import aws_cdk as cdk
from aws_cdk import assertions

from src_infra.stack_infrastructure import InfrastructureStack
from src_infra.stack_backend import BackendStack


def _create_stacks():
    app = cdk.App()
    env_context = {
        "project_name": "rca",
        "ecs": {"cpu": 512, "memory_mib": 1024, "desired_count": 1},
        "bedrock": {"region": "eu-west-1", "models": {"standard": {"model_id": "test-model"}}},
    }
    infra = InfrastructureStack(app, "TestInfra", env_name="test", env_context=env_context)
    backend = BackendStack(
        app, "TestBackend", env_name="test", env_context=env_context, infrastructure=infra,
    )
    return backend


def test_ecs_cluster_created():
    stack = _create_stacks()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ECS::Cluster", {
        "ClusterName": "rca-backend-ecs-cluster-test",
    })


def test_fargate_service_created():
    stack = _create_stacks()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ECS::Service", {
        "ServiceName": "rca-backend-ecs-agent-svc-test",
        "DesiredCount": 1,
        "LaunchType": "FARGATE",
    })


def test_nlb_is_internal():
    stack = _create_stacks()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ElasticLoadBalancingV2::LoadBalancer", {
        "Scheme": "internal",
        "Type": "network",
    })


def test_task_definition_cpu_memory():
    stack = _create_stacks()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ECS::TaskDefinition", {
        "Cpu": "512",
        "Memory": "1024",
    })


def test_container_environment_vars():
    stack = _create_stacks()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ECS::TaskDefinition", {
        "ContainerDefinitions": assertions.Match.array_with([
            assertions.Match.object_like({
                "Environment": assertions.Match.array_with([
                    {"Name": "WS_PORT", "Value": "8080"},
                    {"Name": "BEDROCK_REGION", "Value": "eu-west-1"},
                    {"Name": "BEDROCK_MODEL_ID", "Value": "test-model"},
                ]),
            }),
        ]),
    })


def test_security_group_no_public_ingress():
    stack = _create_stacks()
    template = assertions.Template.from_stack(stack)
    sg_rules = template.find_resources("AWS::EC2::SecurityGroup")
    for _, sg in sg_rules.items():
        ingress = sg.get("Properties", {}).get("SecurityGroupIngress", [])
        for rule in ingress:
            assert rule.get("CidrIp") != "0.0.0.0/0"


def test_log_group_created():
    stack = _create_stacks()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::Logs::LogGroup", {
        "LogGroupName": "/ecs/rca-backend-ecs-agent-svc-test",
        "RetentionInDays": 7,
    })
