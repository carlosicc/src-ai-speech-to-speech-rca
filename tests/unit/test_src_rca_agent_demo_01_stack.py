import aws_cdk as core
import aws_cdk.assertions as assertions

from src_rca_agent_demo_01.src_rca_agent_demo_01_stack import SrcRcaAgentDemo01Stack

# example tests. To run these tests, uncomment this file along with the example
# resource in src_rca_agent_demo_01/src_rca_agent_demo_01_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = SrcRcaAgentDemo01Stack(app, "src-rca-agent-demo-01")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
