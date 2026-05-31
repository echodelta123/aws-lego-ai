"""
model_card_generator.py
-----------------------
Generates standardised model cards from SageMaker Model Registry metadata.

A model card is the key governance artefact that enterprise risk and compliance
teams need before approving a model for production.  It answers:
  - What does this model do?
  - What data was it trained on and when?
  - What are its known limitations and failure modes?
  - What monitoring is in place?
  - Who is responsible for it?

This generator pulls metadata from the SageMaker Model Registry and produces
a human-readable Markdown card plus a machine-readable JSON record.
Both are stored in S3 alongside the model artefacts for full traceability.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)

MODEL_CARDS_BUCKET = os.environ.get("MODEL_CARDS_BUCKET", "ml-governance-model-cards")


@dataclass
class ModelCard:
    model_name: str
    model_version: str
    model_package_arn: str
    intended_use: str
    training_data_description: str
    training_data_version: str
    evaluation_dataset_description: str

    # Metrics from the evaluation job
    evaluation_metrics: dict[str, float] = field(default_factory=dict)

    # Known limitations, edge cases, failure modes
    limitations: list[str] = field(default_factory=list)

    # Bias evaluation summary
    bias_evaluation_summary: str = ""
    disparate_impact_score: float | None = None

    # Operational info
    monitoring_contacts: list[str] = field(default_factory=list)
    endpoint_name: str = ""
    monitoring_dashboard_url: str = ""
    approved_by: str = ""
    approval_date: str = ""

    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_markdown(self) -> str:
        metrics_table = "\n".join(
            f"| {k} | {v:.4f} |"
            for k, v in self.evaluation_metrics.items()
        )
        limitations_list = "\n".join(f"- {l}" for l in self.limitations)
        contacts_list = ", ".join(self.monitoring_contacts) or "Not specified"

        return f"""# Model Card: {self.model_name} v{self.model_version}

> Generated: {self.generated_at}
> Approved by: {self.approved_by} on {self.approval_date}

## Intended Use

{self.intended_use}

## Model Package

- **ARN**: `{self.model_package_arn}`
- **Training Data**: {self.training_data_description} (version: `{self.training_data_version}`)
- **Evaluation Dataset**: {self.evaluation_dataset_description}

## Evaluation Metrics

| Metric | Value |
|--------|-------|
{metrics_table}

## Bias & Fairness

{self.bias_evaluation_summary}

{f"Disparate Impact Score: **{self.disparate_impact_score:.3f}** (acceptable range: 0.8 – 1.25)" if self.disparate_impact_score is not None else ""}

## Known Limitations

{limitations_list if self.limitations else "None documented."}

## Operational

- **Endpoint**: `{self.endpoint_name}`
- **Monitoring Dashboard**: {self.monitoring_dashboard_url}
- **Monitoring Contacts**: {contacts_list}
"""

    def to_dict(self) -> dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)


class ModelCardGenerator:
    def __init__(self) -> None:
        self._sm = boto3.client("sagemaker", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        self._s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-west-1"))

    def generate_and_store(self, model_package_arn: str, extra_metadata: dict[str, Any]) -> str:
        """
        Pull SageMaker metadata, generate the model card, store in S3.

        Returns the S3 URI of the stored card.
        """
        sm_metadata = self._fetch_sagemaker_metadata(model_package_arn)
        card = self._build_card(model_package_arn, sm_metadata, extra_metadata)
        s3_uri = self._store(card)
        logger.info("Model card stored at %s", s3_uri)
        return s3_uri

    def _fetch_sagemaker_metadata(self, arn: str) -> dict[str, Any]:
        response = self._sm.describe_model_package(ModelPackageName=arn)
        return response

    def _build_card(
        self, arn: str, sm_metadata: dict[str, Any], extra: dict[str, Any]
    ) -> ModelCard:
        model_name = sm_metadata.get("ModelPackageGroupName", "unknown")
        model_version = str(sm_metadata.get("ModelPackageVersion", "unknown"))

        # Extract evaluation metrics from SageMaker metadata if available
        metrics: dict[str, float] = {}
        for metric_spec in sm_metadata.get("ModelMetrics", {}).get("ModelQuality", {}).get("Statistics", {}).get("ContentType", []):
            pass  # would parse actual metric JSON here in production
        metrics = extra.get("evaluation_metrics", metrics)

        return ModelCard(
            model_name=model_name,
            model_version=model_version,
            model_package_arn=arn,
            intended_use=extra.get("intended_use", "Not specified"),
            training_data_description=extra.get("training_data_description", "Not specified"),
            training_data_version=extra.get("training_data_version", "unknown"),
            evaluation_dataset_description=extra.get("evaluation_dataset_description", "Not specified"),
            evaluation_metrics=metrics,
            limitations=extra.get("limitations", []),
            bias_evaluation_summary=extra.get("bias_evaluation_summary", "Not evaluated"),
            disparate_impact_score=extra.get("disparate_impact_score"),
            monitoring_contacts=extra.get("monitoring_contacts", []),
            endpoint_name=extra.get("endpoint_name", ""),
            monitoring_dashboard_url=extra.get("monitoring_dashboard_url", ""),
            approved_by=extra.get("approved_by", ""),
            approval_date=extra.get("approval_date", ""),
        )

    def _store(self, card: ModelCard) -> str:
        prefix = f"model-cards/{card.model_name}/v{card.model_version}"
        md_key = f"{prefix}/model_card.md"
        json_key = f"{prefix}/model_card.json"

        self._s3.put_object(
            Bucket=MODEL_CARDS_BUCKET,
            Key=md_key,
            Body=card.to_markdown().encode("utf-8"),
            ContentType="text/markdown",
        )
        self._s3.put_object(
            Bucket=MODEL_CARDS_BUCKET,
            Key=json_key,
            Body=json.dumps(card.to_dict(), default=str).encode("utf-8"),
            ContentType="application/json",
        )
        return f"s3://{MODEL_CARDS_BUCKET}/{md_key}"
