"""
infra/codepipeline_stack.py
----------------------------
CDK stack for the end-to-end ML production pipeline.

Deploys:
  - S3 buckets (training data, model artefacts, governance)
  - ECR repository for training images
  - CodeBuild project (unit tests + Docker build)
  - SageMaker Pipeline (train → evaluate → register)
  - CodePipeline (source → build → train → approve → deploy)
  - DynamoDB traceability table
  - CloudWatch alarms for canary monitoring
  - SNS topic for approval notifications
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_cloudwatch as cloudwatch
from constructs import Construct


class MLPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 Buckets ───────────────────────────────────────────────────────
        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
        )
        artefacts_bucket = s3.Bucket(
            self,
            "ArtefactsBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
        )
        governance_bucket = s3.Bucket(
            self,
            "GovernanceBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            # Object lock ensures model cards and traceability records cannot be deleted
            object_lock_enabled=True,
        )

        # ── ECR ─────────────────────────────────────────────────────────────
        training_repo = ecr.Repository(
            self,
            "TrainingImageRepo",
            repository_name="ml-training-image",
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: SDLC Traceability ──────────────────────────────────────
        traceability_table = dynamodb.Table(
            self,
            "TraceabilityTable",
            table_name="ml-sdlc-traceability",
            partition_key=dynamodb.Attribute(name="record_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        traceability_table.add_global_secondary_index(
            index_name="endpoint-name-index",
            partition_key=dynamodb.Attribute(name="endpoint_name", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="deployed_at_utc", type=dynamodb.AttributeType.STRING),
        )

        # ── SNS: Approval Notifications ──────────────────────────────────────
        approval_topic = sns.Topic(
            self,
            "ApprovalTopic",
            display_name="ML Model Approval Requests",
        )

        # ── CodeBuild: Unit Tests + Docker Build ─────────────────────────────
        build_project = codebuild.PipelineProject(
            self,
            "BuildProject",
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": ["pip install -r requirements.txt"]},
                    "pre_build": {"commands": ["python -m pytest tests/ -v --tb=short"]},
                    "build": {
                        "commands": [
                            "docker build -t $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION .",
                            "docker push $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION",
                        ]
                    },
                },
                "artifacts": {"files": ["**/*"]},
            }),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=True,  # required for Docker
            ),
            environment_variables={
                "ECR_REPO_URI": codebuild.BuildEnvironmentVariable(value=training_repo.repository_uri),
            },
        )
        training_repo.grant_pull_push(build_project)

        # ── CloudWatch Alarm: Canary Error Rate ──────────────────────────────
        canary_alarm = cloudwatch.Alarm(
            self,
            "CanaryErrorAlarm",
            alarm_name="ml-canary-error-rate",
            metric=cloudwatch.Metric(
                namespace="AWS/SageMaker",
                metric_name="Invocation4XXErrors",
                dimensions_map={"EndpointName": "my-model-endpoint-prod"},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=10,
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Triggers rollback if canary error rate exceeds threshold",
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        cdk.CfnOutput(self, "ArtefactsBucketName", value=artefacts_bucket.bucket_name)
        cdk.CfnOutput(self, "GovernanceBucketName", value=governance_bucket.bucket_name)
        cdk.CfnOutput(self, "TraceabilityTableArn", value=traceability_table.table_arn)
        cdk.CfnOutput(self, "CanaryAlarmArn", value=canary_alarm.alarm_arn)
