"""Plans for the tests: the same architecture under any names / CIDRs, and variations of it."""


def web_app(env="staging", app="web", net="10.0", db=True, public_db=False, budget=None) -> dict:
    n = lambda s: f"{env}-{app}-{s}"
    resources = [
        {"kind": "vpc", "name": n("vpc"), "cidr": f"{net}.0.0/16"},
        {"kind": "subnet", "name": n("a"), "cidr": f"{net}.1.0/24", "depends_on": [n("vpc")]},
        {"kind": "subnet", "name": n("b"), "cidr": f"{net}.2.0/24", "depends_on": [n("vpc")]},
        {"kind": "security_group", "name": n("sg"), "depends_on": [n("vpc")],
         "ingress": [{"port": 443, "cidr": "0.0.0.0/0"}]},
        {"kind": "ec2_instance", "name": n("1"), "instance_type": "t3.micro", "depends_on": [n("a"), n("sg")]},
    ]
    if db:
        resources.append({"kind": "rds_instance", "name": n("db"), "instance_type": "db.t3.micro",
                          "engine": "postgres", "public": public_db, "depends_on": [n("sg"), n("a"), n("b")]})
    return {"env": env, "region": "us-east-1", "budget_usd": budget, "resources": resources}
