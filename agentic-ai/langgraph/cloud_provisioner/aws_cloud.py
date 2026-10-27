"""Real AWS provider: the same create/delete as FakeCloud, with boto3.

    uv sync --extra aws
    CLOUD_PROVIDER=aws uv run cli.py        # uses your normal AWS credentials/profile

Try it on LocalStack first (a local AWS emulator) -- boto3 reads the endpoint
from the environment, so no code changes:

    AWS_ENDPOINT_URL=http://localhost:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test

Everything we create is tagged Project=cloud-provisioner, Env=<env>, Name=<name>.
The database password is generated and kept by AWS Secrets Manager
(ManageMasterUserPassword), so no secret ever passes through the LLM or this code.
Real resources cost real money: destroy the env when you are done.
"""

import os
import uuid

import boto3
from botocore.exceptions import ClientError

from catalog import Resource
from cloud import TransientError

TRANSIENT = {"InsufficientInstanceCapacity", "InsufficientDBInstanceCapacity", "Throttling",
             "ThrottlingException", "RequestLimitExceeded", "DependencyViolation"}
AMI_PARAM = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"


def _tags(name: str, env: str) -> list[dict]:
    return [{"Key": "Name", "Value": name}, {"Key": "Env", "Value": env},
            {"Key": "Project", "Value": "cloud-provisioner"}]


def _deps(r: Resource, refs: dict[str, dict], kind: str) -> list[str]:
    return [refs[d]["cloud_id"] for d in r.depends_on if refs.get(d, {}).get("kind") == kind]


class AwsCloud:
    name = "aws"

    def _client(self, service: str, region: str):
        return boto3.client(service, region_name=region)

    def create(self, r: Resource, env: str, region: str, refs: dict[str, dict]) -> str:
        try:
            return getattr(self, f"_create_{r.kind}")(r, env, region, refs)
        except ClientError as e:
            if e.response["Error"]["Code"] in TRANSIENT:
                raise TransientError(str(e)) from e
            raise

    def delete(self, name: str, record: dict) -> None:
        try:
            getattr(self, f"_delete_{record['kind']}")(name, record)
        except ClientError as e:
            if e.response["Error"]["Code"] in TRANSIENT:
                raise TransientError(str(e)) from e
            raise

    # ---- create ---------------------------------------------------------

    def _create_vpc(self, r, env, region, refs):
        ec2 = self._client("ec2", region)
        vpc_id = ec2.create_vpc(CidrBlock=r.cidr, TagSpecifications=[
            {"ResourceType": "vpc", "Tags": _tags(r.name, env)}])["Vpc"]["VpcId"]
        ec2.get_waiter("vpc_available").wait(VpcIds=[vpc_id])
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
        return vpc_id

    def _create_subnet(self, r, env, region, refs):
        ec2 = self._client("ec2", region)
        vpc_name = next(d for d in r.depends_on if refs.get(d, {}).get("kind") == "vpc")
        vpc_id = refs[vpc_name]["cloud_id"]
        # spread subnets of one vpc over availability zones: a, b, c, ...
        zones = [z["ZoneName"] for z in ec2.describe_availability_zones()["AvailabilityZones"]]
        siblings = sum(1 for rec in refs.values()
                       if rec["kind"] == "subnet" and vpc_name in rec["spec"]["depends_on"])
        subnet_id = ec2.create_subnet(
            VpcId=vpc_id, CidrBlock=r.cidr, AvailabilityZone=zones[siblings % len(zones)],
            TagSpecifications=[{"ResourceType": "subnet", "Tags": _tags(r.name, env)}])["Subnet"]["SubnetId"]
        if r.public:  # internet gateway + route table, owned by the vpc (removed in _delete_vpc)
            igws = ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}])
            if igws["InternetGateways"]:
                igw_id = igws["InternetGateways"][0]["InternetGatewayId"]
            else:
                igw_id = ec2.create_internet_gateway(TagSpecifications=[
                    {"ResourceType": "internet-gateway", "Tags": _tags(f"{r.name}-igw", env)}])["InternetGateway"]["InternetGatewayId"]
                ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
            rt_id = ec2.create_route_table(VpcId=vpc_id, TagSpecifications=[
                {"ResourceType": "route-table", "Tags": _tags(f"{r.name}-rt", env)}])["RouteTable"]["RouteTableId"]
            ec2.create_route(RouteTableId=rt_id, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id)
            ec2.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
            ec2.modify_subnet_attribute(SubnetId=subnet_id, MapPublicIpOnLaunch={"Value": True})
        return subnet_id

    def _create_security_group(self, r, env, region, refs):
        ec2 = self._client("ec2", region)
        sg_id = ec2.create_security_group(
            GroupName=r.name, Description=f"{r.name} (cloud-provisioner)", VpcId=_deps(r, refs, "vpc")[0],
            TagSpecifications=[{"ResourceType": "security-group", "Tags": _tags(r.name, env)}])["GroupId"]
        if r.ingress:
            ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=[
                {"IpProtocol": "tcp", "FromPort": i.port, "ToPort": i.port, "IpRanges": [{"CidrIp": i.cidr}]}
                for i in r.ingress])
        return sg_id

    def _create_ec2_instance(self, r, env, region, refs):
        ec2 = self._client("ec2", region)
        ami = os.getenv("AWS_AMI_ID") or self._client("ssm", region).get_parameter(Name=AMI_PARAM)["Parameter"]["Value"]
        instance_id = ec2.run_instances(
            ImageId=ami, InstanceType=r.instance_type, MinCount=1, MaxCount=1,
            SubnetId=_deps(r, refs, "subnet")[0], SecurityGroupIds=_deps(r, refs, "security_group"),
            TagSpecifications=[{"ResourceType": "instance", "Tags": _tags(r.name, env)}],
        )["Instances"][0]["InstanceId"]
        ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
        return instance_id

    def _create_rds_instance(self, r, env, region, refs):
        rds = self._client("rds", region)
        rds.create_db_subnet_group(DBSubnetGroupName=r.name, DBSubnetGroupDescription=r.name,
                                   SubnetIds=_deps(r, refs, "subnet"), Tags=_tags(r.name, env))
        rds.create_db_instance(
            DBInstanceIdentifier=r.name, Engine=r.engine, DBInstanceClass=r.instance_type,
            AllocatedStorage=r.storage_gb or 20, MasterUsername="appadmin", ManageMasterUserPassword=True,
            PubliclyAccessible=False, DBSubnetGroupName=r.name,
            VpcSecurityGroupIds=_deps(r, refs, "security_group"), Tags=_tags(r.name, env))
        rds.get_waiter("db_instance_available").wait(DBInstanceIdentifier=r.name)  # ~5-10 minutes
        return r.name

    def _create_s3_bucket(self, r, env, region, refs):
        s3 = self._client("s3", region)
        bucket = f"{r.name}-{uuid.uuid4().hex[:8]}"  # bucket names are global across all AWS accounts
        kwargs = {} if region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": region}}
        s3.create_bucket(Bucket=bucket, **kwargs)
        s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": _tags(r.name, env)})
        return bucket

    # ---- delete ---------------------------------------------------------

    def _delete_ec2_instance(self, name, rec):
        ec2 = self._client("ec2", rec["region"])
        ec2.terminate_instances(InstanceIds=[rec["cloud_id"]])
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[rec["cloud_id"]])

    def _delete_rds_instance(self, name, rec):
        rds = self._client("rds", rec["region"])
        rds.delete_db_instance(DBInstanceIdentifier=rec["cloud_id"], SkipFinalSnapshot=True,
                               DeleteAutomatedBackups=True)
        rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=rec["cloud_id"])
        rds.delete_db_subnet_group(DBSubnetGroupName=name)

    def _delete_security_group(self, name, rec):
        self._client("ec2", rec["region"]).delete_security_group(GroupId=rec["cloud_id"])

    def _delete_subnet(self, name, rec):
        self._client("ec2", rec["region"]).delete_subnet(SubnetId=rec["cloud_id"])

    def _delete_vpc(self, name, rec):
        ec2, vpc_id = self._client("ec2", rec["region"]), rec["cloud_id"]
        for igw in ec2.describe_internet_gateways(
                Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}])["InternetGateways"]:
            ec2.detach_internet_gateway(InternetGatewayId=igw["InternetGatewayId"], VpcId=vpc_id)
            ec2.delete_internet_gateway(InternetGatewayId=igw["InternetGatewayId"])
        for rt in ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["RouteTables"]:
            if not any(a.get("Main") for a in rt["Associations"]):
                ec2.delete_route_table(RouteTableId=rt["RouteTableId"])
        ec2.delete_vpc(VpcId=vpc_id)

    def _delete_s3_bucket(self, name, rec):
        bucket = boto3.resource("s3", region_name=rec["region"]).Bucket(rec["cloud_id"])
        bucket.objects.all().delete()
        bucket.delete()
