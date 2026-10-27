"""What can be provisioned: the plan model, the AWS-shaped catalog, and the cost estimate.

Resource kinds use AWS names so the same plan runs on the fake cloud (cloud.py)
and on real AWS (aws_cloud.py). Prices are rough us-east-1 on-demand figures
for teaching, not a quote.
"""

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["vpc", "subnet", "security_group", "ec2_instance", "rds_instance", "s3_bucket"]

# creation order; deletes run in reverse
KIND_ORDER: list[str] = ["vpc", "subnet", "security_group", "s3_bucket", "ec2_instance", "rds_instance"]

REGIONS = ["us-east-1", "us-west-2", "eu-west-1"]
ENVS = ["dev", "staging", "prod"]

HOURS_PER_MONTH = 730
EC2_HOURLY = {"t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416, "m5.large": 0.096}
RDS_HOURLY = {"db.t3.micro": 0.017, "db.t3.small": 0.034, "db.t3.medium": 0.068}
RDS_STORAGE_GB_MONTH = 0.115
S3_GB_MONTH = 0.023


class Ingress(BaseModel):
    port: int
    cidr: str = Field(description="who may connect, e.g. 10.0.0.0/16 or 0.0.0.0/0")


class Resource(BaseModel):
    kind: Kind
    name: str = Field(description="unique, must start with the env, e.g. staging-web-1")
    depends_on: list[str] = Field(default_factory=list, description="names of resources this one needs")
    cidr: str | None = Field(None, description="vpc / subnet address range")
    public: bool = Field(False, description="subnet with internet route, public database, public bucket")
    ingress: list[Ingress] = Field(default_factory=list, description="security_group inbound rules")
    instance_type: str | None = Field(None, description="ec2: t3.micro..., rds: db.t3.micro...")
    engine: str | None = Field(None, description="rds: postgres or mysql")
    storage_gb: int | None = Field(None, description="rds disk or expected s3 size")


class Plan(BaseModel):
    env: Literal["dev", "staging", "prod"]
    region: str
    budget_usd: float | None = Field(None, description="monthly budget the user gave, if any")
    resources: list[Resource]


def monthly_cost(r: Resource) -> float:
    if r.kind == "ec2_instance":
        return EC2_HOURLY.get(r.instance_type or "", 0) * HOURS_PER_MONTH
    if r.kind == "rds_instance":
        return RDS_HOURLY.get(r.instance_type or "", 0) * HOURS_PER_MONTH + (r.storage_gb or 20) * RDS_STORAGE_GB_MONTH
    if r.kind == "s3_bucket":
        return (r.storage_gb or 10) * S3_GB_MONTH
    return 0.0  # vpc, subnet, security_group are free


def estimate(plan: Plan) -> dict:
    lines = {r.name: round(monthly_cost(r), 2) for r in plan.resources}
    return {"lines": lines, "total": round(sum(lines.values()), 2), "currency": "USD/month"}


def ordered(resources: list[Resource]) -> list[Resource]:
    """Dependencies first: by kind, then by depends_on within a kind."""
    by_name = {r.name: r for r in resources}
    done: list[Resource] = []

    def visit(r: Resource, path: tuple = ()):
        if r in done or r.name in path:
            return
        for dep in r.depends_on:
            if dep in by_name:
                visit(by_name[dep], (*path, r.name))
        done.append(r)

    for r in sorted(resources, key=lambda r: KIND_ORDER.index(r.kind)):
        visit(r)
    return done


def catalog_text() -> str:
    ec2 = ", ".join(f"{t} ${p * HOURS_PER_MONTH:.0f}" for t, p in EC2_HOURLY.items())
    rds = ", ".join(f"{t} ${p * HOURS_PER_MONTH:.0f}" for t, p in RDS_HOURLY.items())
    return (
        f"regions: {', '.join(REGIONS)}\nenvs: {', '.join(ENVS)}\n"
        f"ec2_instance types (per month): {ec2}\n"
        f"rds_instance types (per month, + ${RDS_STORAGE_GB_MONTH}/GB): {rds}; engines: postgres, mysql\n"
        f"s3_bucket: ${S3_GB_MONTH}/GB-month\nvpc, subnet, security_group: free"
    )
