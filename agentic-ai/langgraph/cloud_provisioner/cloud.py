"""The cloud the graph talks to: an inventory (our "state file") plus a provider.

  Inventory    inventory.db -- name -> {kind, env, region, cloud_id, spec}.
               Like a Terraform state file: the provider creates things, the
               inventory remembers what we created so we can list and destroy it.
  FakeCloud    default. No credentials, no cost, short delays, and one flaky
               kind (rds_instance fails its first attempt) to show retries.
  AwsCloud     aws_cloud.py, same two methods, real boto3 calls.

    CLOUD_PROVIDER=fake   (default)
    CLOUD_PROVIDER=aws    real AWS, see aws_cloud.py and README "Real AWS"
"""

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

from catalog import Resource

HERE = Path(__file__).parent
ID_PREFIX = {"vpc": "vpc", "subnet": "subnet", "security_group": "sg",
             "ec2_instance": "i", "rds_instance": "db", "s3_bucket": "s3"}


class TransientError(Exception):
    """Worth retrying (capacity, throttling)."""


class Inventory:
    def __init__(self, path: Path = HERE / "inventory.db"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("""create table if not exists resources (
            name text primary key, kind text, env text, region text,
            cloud_id text, spec text, created_at real)""")

    def all(self) -> dict[str, dict]:
        rows = self.db.execute("select name, kind, env, region, cloud_id, spec from resources").fetchall()
        return {n: {"kind": k, "env": e, "region": rg, "cloud_id": c, "spec": json.loads(s)}
                for n, k, e, rg, c, s in rows}

    def add(self, r: Resource, env: str, region: str, cloud_id: str):
        self.db.execute("insert or replace into resources values (?,?,?,?,?,?,?)",
                        (r.name, r.kind, env, region, cloud_id, r.model_dump_json(), time.time()))
        self.db.commit()

    def remove(self, name: str):
        self.db.execute("delete from resources where name = ?", (name,))
        self.db.commit()


class FakeCloud:
    name = "fake"

    def __init__(self):
        self.delay = float(os.getenv("FAKE_DELAY", "0.8"))
        self.flaky = set(os.getenv("FAKE_FLAKY", "rds_instance").split(","))
        self._failed_once: set[str] = set()

    def create(self, r: Resource, env: str, region: str, refs: dict[str, dict]) -> str:
        """refs: inventory records of everything already created (for depends_on ids)."""
        time.sleep(self.delay * (3 if r.kind == "rds_instance" else 1))
        if r.kind in self.flaky and r.name not in self._failed_once:
            self._failed_once.add(r.name)
            raise TransientError(f"InsufficientCapacity: no {r.instance_type} capacity in {region}, try again")
        return f"{ID_PREFIX[r.kind]}-{uuid.uuid4().hex[:10]}"

    def delete(self, name: str, record: dict) -> None:
        time.sleep(self.delay / 2)


def get_provider():
    if os.getenv("CLOUD_PROVIDER", "fake") == "aws":
        from aws_cloud import AwsCloud
        return AwsCloud()
    return FakeCloud()
