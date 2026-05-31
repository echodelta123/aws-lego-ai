"""
pipeline/sagemaker_pipeline.py
-------------------------------
Defines and executes the SageMaker Pipeline: preprocessing → training → evaluation → conditional registration.

The pipeline is parameterised so the same definition can be used for different
data versions and triggered with different commit metadata.  All parameters
are recorded in the model registry for full traceability.

Pipeline steps:
  1. Preprocessing  — run data quality checks; transform raw data to feature format
  2. Training       — train the model using the parameterised training image
  3. Evaluation     — compute accuracy, F1, AUC; run Clarify bias check
  4. Registration   — register to Model Registry with status PendingManualApproval
                      (only if evaluation metrics meet minimum thresholds)
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone

import boto3
import sagemaker
from sagemaker.processing import ProcessingInput, ProcessingOutput, ScriptProcessor
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.functions import JsonGet
from sagemaker.workflow.model_step import ModelStep
from sagemaker.workflow.parameters import ParameterFloat, ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.steps import ProcessingStep, TrainingStep

logger = logging.getLogger(__name__)

PIPELINE_NAME = "ml-training-pipeline"
MIN_ACCURACY_THRESHOLD = 0.85  # reject registration if accuracy below this


def build_pipeline(
    role_arn: str,
    data_uri: str,
    training_image_uri: str,
    model_package_group_name: str,
    git_commit_sha: str,
    jira_ticket: str,
) -> Pipeline:
    """
    Build a SageMaker Pipeline for training and conditional model registration.
    The pipeline is defined as code and version-controlled alongside the model code.
    """
    session = PipelineSession()

    # Pipeline parameters — can be overridden at execution time without redefining the pipeline
    param_data_uri = ParameterString(name="DataUri", default_value=data_uri)
    param_min_accuracy = ParameterFloat(name="MinAccuracyThreshold", default_value=MIN_ACCURACY_THRESHOLD)
    param_git_commit = ParameterString(name="GitCommitSha", default_value=git_commit_sha)
    param_jira_ticket = ParameterString(name="JiraTicket", default_value=jira_ticket)

    # Step 1: Preprocessing
    preprocessor = SKLearnProcessor(
        framework_version="1.2-1",
        instance_type="ml.m5.large",
        instance_count=1,
        role=role_arn,
        sagemaker_session=session,
    )
    preprocessing_step = ProcessingStep(
        name="Preprocessing",
        processor=preprocessor,
        inputs=[ProcessingInput(source=param_data_uri, destination="/opt/ml/processing/input")],
        outputs=[
            ProcessingOutput(output_name="train", source="/opt/ml/processing/train"),
            ProcessingOutput(output_name="validation", source="/opt/ml/processing/validation"),
        ],
        code="scripts/preprocessing.py",
    )

    # Step 2: Training
    from sagemaker.estimator import Estimator

    estimator = Estimator(
        image_uri=training_image_uri,
        instance_type="ml.m5.xlarge",
        instance_count=1,
        role=role_arn,
        sagemaker_session=session,
        tags=[
            {"Key": "GitCommit", "Value": git_commit_sha},
            {"Key": "JiraTicket", "Value": jira_ticket},
        ],
    )
    training_step = TrainingStep(
        name="Training",
        estimator=estimator,
        inputs={
            "train": sagemaker.TrainingInput(
                s3_data=preprocessing_step.properties.ProcessingOutputConfig.Outputs["train"].S3Output.S3Uri
            ),
            "validation": sagemaker.TrainingInput(
                s3_data=preprocessing_step.properties.ProcessingOutputConfig.Outputs["validation"].S3Output.S3Uri
            ),
        },
    )

    # Step 3: Evaluation
    evaluator = ScriptProcessor(
        image_uri=training_image_uri,
        command=["python3"],
        instance_type="ml.m5.large",
        instance_count=1,
        role=role_arn,
        sagemaker_session=session,
    )
    evaluation_step = ProcessingStep(
        name="Evaluation",
        processor=evaluator,
        inputs=[
            ProcessingInput(
                source=training_step.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            ),
        ],
        outputs=[
            ProcessingOutput(output_name="evaluation", source="/opt/ml/processing/evaluation"),
        ],
        code="scripts/evaluation.py",
        property_files=[
            sagemaker.workflow.properties.PropertyFile(
                name="EvaluationReport",
                output_name="evaluation",
                path="evaluation.json",
            )
        ],
    )

    # Step 4: Conditional Registration (only if accuracy >= threshold)
    # Registration is deferred to the CodePipeline approval stage in practice —
    # this shows the pattern for automated quality gating.
    accuracy_condition = ConditionGreaterThanOrEqualTo(
        left=JsonGet(
            step_name=evaluation_step.name,
            property_file="EvaluationReport",
            json_path="metrics.accuracy.value",
        ),
        right=param_min_accuracy,
    )

    condition_step = ConditionStep(
        name="CheckAccuracyThreshold",
        conditions=[accuracy_condition],
        if_steps=[],   # Registration happens via CodePipeline approval; set here if fully automated
        else_steps=[],  # Pipeline ends without registration — CodePipeline stage fails
    )

    pipeline = Pipeline(
        name=PIPELINE_NAME,
        parameters=[param_data_uri, param_min_accuracy, param_git_commit, param_jira_ticket],
        steps=[preprocessing_step, training_step, evaluation_step, condition_step],
        sagemaker_session=session,
    )
    return pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-uri", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--jira-ticket", required=True)
    args = parser.parse_args()

    role_arn = os.environ["SAGEMAKER_EXECUTION_ROLE_ARN"]
    training_image_uri = os.environ["TRAINING_IMAGE_URI"]
    model_package_group = os.environ.get("MODEL_PACKAGE_GROUP", "my-model")

    pipeline = build_pipeline(
        role_arn=role_arn,
        data_uri=args.data_uri,
        training_image_uri=training_image_uri,
        model_package_group_name=model_package_group,
        git_commit_sha=args.commit_sha,
        jira_ticket=args.jira_ticket,
    )

    pipeline.upsert(role_arn=role_arn)
    execution = pipeline.start(
        parameters={
            "DataUri": args.data_uri,
            "GitCommitSha": args.commit_sha,
            "JiraTicket": args.jira_ticket,
        }
    )
    logger.info("Pipeline execution started: %s", execution.arn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
