"""Guardrails in plain code. The LLM proposes; these rules decide, every time.

check_create / check_destroy return a list of human-readable problems
(empty = allowed). The graph sends them back to the LLM to fix the plan.
"""

from catalog import EC2_HOURLY, REGIONS, RDS_HOURLY, Plan

MAX_EC2_PER_ENV = 4
ADMIN_PORTS = {22, 3389, 5432, 3306}
# what each kind must live in (AWS needs these ids to create it)
REQUIRED_DEPS = {"subnet": ["vpc"], "security_group": ["vpc"],
                 "ec2_instance": ["subnet", "security_group"], "rds_instance": ["security_group"]}


def check_create(plan: Plan, inventory: dict[str, dict]) -> list[str]:
    issues = []
    names = [r.name for r in plan.resources]
    by_name = {r.name: r for r in plan.resources}
    existing = {n for n, rec in inventory.items() if rec["env"] == plan.env}

    if plan.region not in REGIONS:
        issues.append(f"region {plan.region} is not allowed; use one of {REGIONS}")
    if not plan.resources:
        issues.append("plan has no resources")
    for n in {n for n in names if names.count(n) > 1}:
        issues.append(f"name {n} is used twice")

    for r in plan.resources:
        if not r.name.startswith(f"{plan.env}-"):
            issues.append(f"{r.name}: name must start with '{plan.env}-'")
        if r.name in inventory:
            issues.append(f"{r.name}: already exists")
        for dep in r.depends_on:
            if dep not in by_name and dep not in existing:
                issues.append(f"{r.name}: depends on unknown resource {dep}")

        if r.kind in ("vpc", "subnet") and not r.cidr:
            issues.append(f"{r.name}: {r.kind} needs a cidr")
        dep_kinds = {(by_name[d].kind if d in by_name else inventory.get(d, {}).get("kind")) for d in r.depends_on}
        for need in REQUIRED_DEPS.get(r.kind, []):
            if need not in dep_kinds:
                issues.append(f"{r.name}: {r.kind} must depend on a {need}")
        if r.kind == "security_group":
            for rule in r.ingress:
                if rule.cidr == "0.0.0.0/0" and rule.port in ADMIN_PORTS:
                    issues.append(f"{r.name}: port {rule.port} must not be open to the internet")
        if r.kind == "ec2_instance" and r.instance_type not in EC2_HOURLY:
            issues.append(f"{r.name}: instance_type must be one of {list(EC2_HOURLY)}")
        if r.kind == "rds_instance":
            if r.instance_type not in RDS_HOURLY:
                issues.append(f"{r.name}: instance_type must be one of {list(RDS_HOURLY)}")
            if r.engine not in ("postgres", "mysql"):
                issues.append(f"{r.name}: engine must be postgres or mysql")
            if r.public:
                issues.append(f"{r.name}: databases must not be public")
            subnets = [d for d in r.depends_on if (by_name.get(d) and by_name[d].kind == "subnet")
                       or inventory.get(d, {}).get("kind") == "subnet"]
            if len(subnets) < 2:
                issues.append(f"{r.name}: rds_instance must depend on 2 subnets (AWS needs 2 availability zones)")
        if r.kind == "s3_bucket" and r.public:
            issues.append(f"{r.name}: buckets must not be public")

    ec2_total = sum(r.kind == "ec2_instance" for r in plan.resources) + sum(
        rec["kind"] == "ec2_instance" for n, rec in inventory.items() if rec["env"] == plan.env
    )
    if ec2_total > MAX_EC2_PER_ENV:
        issues.append(f"quota: at most {MAX_EC2_PER_ENV} ec2_instance per env ({plan.env} would have {ec2_total})")
    return issues


def check_budget(plan: Plan, cost: dict) -> list[str]:
    if plan.budget_usd is not None and cost["total"] > plan.budget_usd:
        return [f"estimated ${cost['total']}/month is over the ${plan.budget_usd} budget; choose smaller or fewer resources"]
    return []


def check_destroy(env: str, inventory: dict[str, dict]) -> list[str]:
    if env == "prod":
        return ["destroying prod is not allowed from the assistant; open a change request"]
    if not any(rec["env"] == env for rec in inventory.values()):
        return [f"nothing to destroy in {env}"]
    return []
