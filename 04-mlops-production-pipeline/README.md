# Project 4: Production MLOps Pipeline

## MLOps Continuous Delivery & Training Pipeline

This project implements the automated continuous integration and delivery (CI/CD) engine of the platform. It manages GNN model retraining and CD deployment with the same rigor as application code — automating the workflow from raw customer interaction events to a validated, live production endpoint.

The pipeline implements a complete ML delivery pipeline where model assets are treated as software artifacts — built, tested, registered, approved, and deployed through a structured, reproducible process with built-in auditability.

As a part of the unified LEGO CX Platform:
- **Ecosystem Integration**: Automatically pre-processes graph structures, retrains, and registers the **SageMaker GNN (LightGCN) model** queried by the Bedrock recommendation agent in [Project 1](../01-lego-recommendation-engine/README.md).
- **Data Pipeline Trigger**: Consumes user interaction edges from the S3 Data Lake (populated by Project 1's Kinesis behavioral stream) to trigger preprocessing and retraining jobs.
- **Governed Promotion**: Once evaluation steps satisfy the target validation metric threshold, the model is registered in the SageMaker Model Registry, triggering a promotion request. Approved models are promoted to production via a CDK-driven blue/green canary rollout.

---

## Architecture

```
Trigger: S3 graph data update OR Git commit
        │
        ▼
AWS CodePipeline
  │
  ├── Stage 1: Source
  │     ├── CodeCommit (model code, training scripts)
  │     └── S3 (interaction data, triggered by EventBridge)
  │
  ├── Stage 2: Build & Test (CodeBuild)
  │     ├── Unit tests
  │     ├── Graph quality checks (Great Expectations)
  │     └── Build Docker training image → ECR
  │
  ├── Stage 3: Train & Evaluate (SageMaker Pipeline)
  │     ├── Preprocessing step (bipartite graph formatting)
  │     ├── Training step (PyTorch Geometric GNN training)
  │     ├── Evaluation step (accuracy/recall metrics, bias check)
  │     └── Register to Model Registry (status: PendingManualApproval)
  │
  ├── Stage 4: Manual Approval Gate
  │     ├── SNS notification to governance team
  │     ├── Evaluation report link in approval request
  │     └── ❌ REJECT → pipeline stops
  │         ✅ APPROVE → proceed to deployment
  │
  └── Stage 5: Deploy (Blue/Green)
        ├── Create new SageMaker endpoint config
        ├── Canary: 10% traffic to new model
        ├── CloudWatch alarm watches error rate (30 min)
        └── Auto-rollback if alarm triggers
            Full traffic shift if alarm stays green
```

---

## SDLC Traceability Matrix

Every production deployment generates an immutable traceability record linking:

| Field | Value (example) |
|-------|----------------|
| Jira Ticket | `AI-247` |
| Git Commit | `a3f9e21` |
| Training Data Version | `s3://data/features/v2024-11-01/` |
| Model Package ARN | `arn:aws:sagemaker:...:model-package/my-model/7` |
| Evaluation Metrics | `{"accuracy": 0.943, "f1": 0.921}` |
| Approval Record | `Approved by: governance-signoff@company.com at 2024-11-05T14:32Z` |
| Model Card URI | `s3://governance/model-cards/my-model/v7/model_card.md` |
| Deployed Endpoint | `my-model-endpoint-prod` |

This record is written to DynamoDB at deployment time and is the authoritative source for compliance audits.

---

## Key Files

| File | Purpose |
|------|---------|
| `pipeline/sagemaker_pipeline.py` | Defines the SageMaker training/evaluation/registration pipeline |
| `pipeline/model_registry.py` | Helper for registering models, recording approval metadata |
| `pipeline/canary_deployer.py` | Blue/green deployment with auto-rollback on CloudWatch alarm |
| `pipeline/traceability_recorder.py` | Writes the SDLC traceability record to DynamoDB |
| `infra/codepipeline_stack.py` | CDK stack for the full CodePipeline + supporting resources |
| `tests/test_canary_deployer.py` | Unit tests for deployment and rollback logic |
| `tests/test_traceability_recorder.py` | Unit tests for the SDLC record writer |
| `docs/sdlc-integration.md` | How this pipeline integrates with the existing SDLC toolchain |

---

## Automated Deployment Governance

Deploying a new model version requires systematic checkpoints before production traffic shifting:

1. **Quality Gates** — Prevents deployment of models whose accuracy or recall metrics do not exceed baseline validation thresholds.
2. **Immutable Audit Lineage** — Creates a verifiable registry record tracing who approved a model, matching it with the specific git commit, training data snapshot, and evaluation report.
3. **Pre-Release Verification** — Allows compliance and operations teams to verify the generated model card and bias report before the model endpoint goes live.

---

## Setup

```bash
pip install -r requirements.txt
python -m pytest tests/ -v

# Deploy the CodePipeline stack
cd infra && cdk deploy MLPipelineStack

# Trigger a pipeline run manually
python pipeline/sagemaker_pipeline.py \
  --data-uri s3://my-data/features/latest/ \
  --commit-sha $(git rev-parse HEAD) \
  --jira-ticket AI-247
```

---

## Infrastructure Cost Optimization & Resource Efficiency

To eliminate baseline compute overhead and optimize resources in non-production environments:
- **On-Demand Ephemeral Pipeline Executions** — SageMaker Pipeline nodes (preprocessing, training, and evaluation) run on ephemeral instances (`ml.m5.large`/`ml.m5.xlarge`) that provision only during pipeline execution. Once complete, resources are automatically terminated, ensuring **$0.00/month** base idle compute costs.
- **Spot Instances for Training Runs** — Ephemeral model retraining stages are configured to use EC2 Spot instances, reducing active training run compute costs by up to 90%.
- **Serverless Pipeline Management** — CodePipeline and CodeBuild orchestrators run fully serverless, scaling to zero when the repository and S3 ingestion paths are inactive.
