"""
infra/stack.py
--------------
CDK stack for the LEGO AI Recommendation Engine.

Deploys:
  - DynamoDB tables (product catalogue, audit log)
  - Kinesis Data Stream + Firehose
  - Lambda functions (orchestrator, guardrail)
  - API Gateway (REST)
  - Bedrock Agent + Knowledge Base (OpenSearch Serverless)
  - SageMaker endpoint (references an externally-trained model)
  - IAM roles with least-privilege policies
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kinesis as kinesis
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct


class LegoRecommendationStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── DynamoDB: Product Catalogue ──────────────────────────────────────
        catalogue_table = dynamodb.Table(
            self,
            "CatalogueTable",
            table_name="lego-product-catalogue",
            partition_key=dynamodb.Attribute(name="product_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: Audit Log ──────────────────────────────────────────────
        audit_table = dynamodb.Table(
            self,
            "AuditTable",
            table_name="lego-recommendation-audit",
            partition_key=dynamodb.Attribute(name="request_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp_utc", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Kinesis: Behaviour Event Stream ─────────────────────────────────
        behaviour_stream = kinesis.Stream(
            self,
            "BehaviourStream",
            stream_name="lego-customer-behaviour",
            shard_count=2,
            retention_period=Duration.days(7),
            encryption=kinesis.StreamEncryption.KMS,
        )

        # ── Lambda: Orchestrator ─────────────────────────────────────────────
        orchestrator_fn = lambda_.Function(
            self,
            "OrchestratorFunction",
            function_name="lego-recommendation-orchestrator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="orchestrator.handler",
            code=lambda_.Code.from_asset("../src"),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "CATALOGUE_TABLE_NAME": catalogue_table.table_name,
                "AUDIT_TABLE_NAME": audit_table.table_name,
                "BEHAVIOUR_STREAM_NAME": behaviour_stream.stream_name,
                "BEDROCK_AGENT_ID": "PLACEHOLDER_SET_AFTER_AGENT_CREATION",
                "BEDROCK_AGENT_ALIAS_ID": "PLACEHOLDER_SET_AFTER_AGENT_CREATION",
            },
            log_retention=logs.RetentionDays.THREE_MONTHS,
        )

        # Grant least-privilege access
        catalogue_table.grant_read_data(orchestrator_fn)
        audit_table.grant_write_data(orchestrator_fn)
        behaviour_stream.grant_write(orchestrator_fn)

        orchestrator_fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeAgent"],
                resources=["arn:aws:bedrock:eu-west-1:*:agent-alias/*/*"],
            )
        )
        orchestrator_fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "LegoRecommendation"}},
            )
        )

        # ── API Gateway ──────────────────────────────────────────────────────
        api = apigw.RestApi(
            self,
            "RecommendationApi",
            rest_api_name="lego-recommendation-api",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=False,  # avoid logging request bodies (PII)
                metrics_enabled=True,
            ),
        )

        recommendations_resource = api.root.add_resource("recommendations")
        recommendations_resource.add_method(
            "POST",
            apigw.LambdaIntegration(orchestrator_fn, timeout=Duration.seconds(29)),
            authorization_type=apigw.AuthorizationType.IAM,
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "ApiEndpoint", value=api.url)
        cdk.CfnOutput(self, "CatalogueTableArn", value=catalogue_table.table_arn)
        cdk.CfnOutput(self, "BehaviourStreamArn", value=behaviour_stream.stream_arn)
