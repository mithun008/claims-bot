from aws_cdk import (
    # Duration,
    RemovalPolicy,
    Stack,
    # aws_sqs as sqs,
    aws_s3 as s3,
    aws_b2bi as b2bi,
    aws_events as events,
    aws_events_targets as targets,
    Duration,
)
from constructs import Construct
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
import os


class ClaimsBotStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here

        # create input bucket
        edi_bucket = s3.Bucket(
            self, "claims-remit-bucket", bucket_name="claims-remit-bucket"
        )
        edi_bucket.apply_removal_policy(RemovalPolicy.RETAIN)
        # enable eventbridge notification for the bucket
        edi_bucket.enable_event_bridge_notification()
        # add permissions for B2B I to access the bucket
        policy_statement = iam.PolicyStatement(
            actions=["s3:*"],
            resources=[edi_bucket.arn_for_objects("*")],
            principals=[iam.ServicePrincipal("b2bi.amazonaws.com")],
        )

        # add bucket policy
        edi_bucket.add_to_resource_policy(policy_statement)

        # create the 837 EDI transformer
        claim_cfn_transformer = b2bi.CfnTransformer(
            self,
            "MyCfnTransformer",
            edi_type=b2bi.CfnTransformer.EdiTypeProperty(
                x12_details=b2bi.CfnTransformer.X12DetailsProperty(
                    transaction_set="X12_837_X222", version="VERSION_5010_HIPAA"
                )
            ),
            file_format="JSON",
            mapping_template="",
            name="prof-claim-transformer",
            status="active",
            sample_document="s3://claims-remit-bucket/837-en-edi.txt",
        )
        # create the 835 EDI transformer
        remit_cfn_transformer = b2bi.CfnTransformer(
            self,
            "ClaimPaymentTransformer",
            edi_type=b2bi.CfnTransformer.EdiTypeProperty(
                x12_details=b2bi.CfnTransformer.X12DetailsProperty(
                    transaction_set="X12_835_X221", version="VERSION_5010_HIPAA"
                )
            ),
            file_format="JSON",
            mapping_template="",
            name="claim-payment-transformer",
            status="active",
            sample_document="s3://claims-remit-bucket/835-en-edi.txt",
        )

        # create bucket for FHIR templates
        fhir_template_bucket = s3.Bucket(
            self, "fhir-template-bucket", bucket_name="fhir-templates-edi"
        )
        lambda_layer = self.create_lambda_layer()

        self.create_event_bridge_rules(
            claim_transformer_id=claim_cfn_transformer.attr_transformer_id,
            remit_transformer_id=remit_cfn_transformer.attr_transformer_id,
            edi_bucket=edi_bucket,
            fhir_template_bucket=fhir_template_bucket,
            lambda_layer=lambda_layer,
        )
        self.create_function_for_bedrock_agent(lambda_layer=lambda_layer)

    def create_function_for_bedrock_agent(self, lambda_layer):
        healthlake_id = os.environ.get("HEALTHLAKE_ID")
        # create a Lambda function to be triggered by Bedrock Agent
        lambda_function = lambda_.Function(
            self,
            "ClaimsRemitLambdaForBedrockAgent",
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler="bedrock_agent.main",
            code=lambda_.Code.from_asset("./lambda/python"),
            layers=[lambda_layer],
            timeout=Duration.seconds(100),
        )
        # add environment variables to the lambda function
        lambda_function.add_environment("HEALTHLAKE_ID", healthlake_id)

        #add permission to invoke Healthlake
        lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["healthlake:SearchWithGet","healthlake:ReadResource"],
                resources=["*"],
            )
        )

        # add policy to allow bedrock agent to invoke
        # Attach the resource-based policy to the Lambda function
        lambda_function.add_permission(
            "AllowBedrockToInvokeLambda",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account,
        )

    def create_lambda_layer(self):
        # create a Lambda layer for python dependencies
        lambda_layer = lambda_.LayerVersion(
            self,
            "ClaimsRemitLambdaLayer",
            code=lambda_.Code.from_asset("./lambda-layer"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_10],
            removal_policy=RemovalPolicy.RETAIN,
            description="Python dependencies for Claims Remit",
            layer_version_name="ClaimsRemitLambdaLayer",
        )
        return lambda_layer

    def create_event_bridge_rules(
        self,
        claim_transformer_id,
        remit_transformer_id,
        edi_bucket,
        fhir_template_bucket,
        lambda_layer,
    ):
        # create event bridge rule for edi intake from s3 with prefix

        event_bridge_rule = events.Rule(
            self,
            "ClaimsRemitInputRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": ["claims-remit-bucket"]},
                    "object": {"key": [{"prefix": "input"}]},
                },
            ),
        )

        # create Lambda function to be triggered by the event bridge rule
        b2bi_lambda_function = lambda_.Function(
            self,
            "ClaimsRemitLambdaToTriggerB2BI",
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler="b2bi_trigger.main",
            code=lambda_.Code.from_asset("./lambda/python"),
            timeout=Duration.seconds(100),
        )
        # add environment variables to the lambda function
        b2bi_lambda_function.add_environment(
            "CLAIM_TRANSFORMER_ID", claim_transformer_id
        )
        b2bi_lambda_function.add_environment(
            "REMIT_TRANSFORMER_ID", remit_transformer_id
        )
        b2bi_lambda_function.add_environment(
            "OUTPUT_BUCKET_NAME", "claims-remit-bucket"
        )
        # add permission to the lambda function to invoke the B2BI transformer
        b2bi_lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["b2bi:StartTransformerJob"],
                resources=["*"],
            )
        )
        # add permission to the lambda function to read s3 bucket
        b2bi_lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:*"],
                resources=[edi_bucket.arn_for_objects("*")],
            )
        )

        event_bridge_rule.add_target(targets.LambdaFunction(b2bi_lambda_function))

        # create event bridge rule for edi output
        event_bridge_rule = events.Rule(
            self,
            "ClaimsRemitOutputRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": ["claims-remit-bucket"]},
                    # event pattern with OR condition
                    "object": {
                        "key": [{"prefix": "output/837"}, {"prefix": "output/835"}]
                    },
                },
            ),
        )

        # create Lambda function to be triggered by the event bridge rule
        # Get the parameter value from the environment variable
        healthlake_id = os.environ.get("HEALTHLAKE_ID")

        fhir_lambda_function = lambda_.Function(
            self,
            "ClaimsRemitLambdaForFHIRTransform",
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler="healthlake_loader.transform_to_FHIR",
            code=lambda_.Code.from_asset("./lambda/python"),
            timeout=Duration.seconds(100),
            layers=[lambda_layer],
        )
        fhir_lambda_function.add_environment(
            "FHIR_TEMPLATE_BUCKET", fhir_template_bucket.bucket_name
        )

        fhir_lambda_function.add_environment("HL_DATASTORE_ID", healthlake_id)

        # add permission to read from S3 bucket
        fhir_lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:*"],
                resources=[
                    fhir_template_bucket.arn_for_objects("*"),
                    edi_bucket.arn_for_objects("*"),
                ],
            )
        )
        # add permission to invoke Healthlake API
        fhir_lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["healthlake:CreateResource"],
                resources=["*"],
            )
        )

        event_bridge_rule.add_target(targets.LambdaFunction(fhir_lambda_function))
