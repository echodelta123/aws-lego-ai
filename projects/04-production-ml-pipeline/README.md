# Project 4: Production ML Pipeline — MLOps & SDLC Integration

## What This Project Shows

This project answers the most enterprise-specific requirement in the job description: **"transitioning from proof-of-concept to production AI systems"** with full **SDLC traceability**, **DevOps integration**, and **approval gates**.

It implements a complete ML delivery pipeline where models are treated with the same rigour as application code — built, tested, registered, approved, and deployed through a governed process.

---

## Architecture

```
Trigger: S3 data update OR Git commit
        │
        ▼
AWS CodePipeline
  │
  ├── Stage 1: Source
  │     ├── CodeCommit (model code, training scripts)
  │     └── S3 (training data, triggered by EventBridge)
  │
  ├── Stage 2: Build & Test (CodeBuild)
  │     ├── Unit tests
  │     ├── Data quality checks (Great Expectations)
  │     └── Build Docker training image → ECR
  │
  ├── Stage 3: Train & Evaluate (SageMaker Pipeline)
  │     ├── Preprocessing step
  │     ├── Training step
  │     ├── Evaluation step (metrics, bias check)
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

Every production deployment includes a traceability record linking:

| Field | Value (example) |
|-------|----------------|
| Jira Ticket | `AI-247` |
| Git Commit | `a3f9e21` |
| Training Data Version | `s3://data/features/v2024-11-01/` |
| Model Package ARN | `arn:aws:sagemaker:...:model-package/my-model/7` |
| Evaluation Metrics | `{"accuracy": 0.943, "f1": 0.921}` |
| Approval Record | `Approved by: john.smith@company.com at 2024-11-05T14:32Z` |
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

## Why the Approval Gate Matters

In a critical national infrastructure context, deploying a new model version without a human review step is unacceptable.  The approval gate:

1. Prevents automated deployment of under-performing models (evaluation metrics are included in the approval request)
2. Creates an immutable record of who approved what, when, and why
3. Allows the governance team to review the model card and bias evaluation before production traffic hits the new model
4. Means there's always a named individual accountable for each production model version

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
