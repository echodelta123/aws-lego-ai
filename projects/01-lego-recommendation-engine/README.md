# Project 1: LEGO AI Recommendation & Customer Behaviour Engine

## What This Project Shows

This project integrates an **AWS Bedrock agentic assistant** with a **SageMaker collaborative-filtering recommendation model** to personalise product discovery for LEGO's e-commerce platform.

It is built to production standards: structured model I/O, full audit logging, hallucination guardrails, and a real-time behavioural data pipeline.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Customer-Facing Layer                                          │
│                                                                 │
│  Browser/App ──► API Gateway ──► Lambda Orchestrator           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────────┐
           │               │                   │
           ▼               ▼                   ▼
  ┌─────────────┐  ┌──────────────┐   ┌─────────────────┐
  │  Bedrock    │  │  SageMaker   │   │  Kinesis Data   │
  │  Agent      │  │  Endpoint    │   │  Stream         │
  │  (Claude 3) │  │  (ColabFilt) │   │  (events)       │
  └──────┬──────┘  └──────┬───────┘   └────────┬────────┘
         │                │                     │
         │  Action Groups │                     │ Firehose
         │  ┌─────────────┘                     ▼
         │  │                          ┌─────────────────┐
         │  ▼                          │  S3 Data Lake   │
         │  ProductSearch              └────────┬────────┘
         │  BehaviourLookup                     │ Glue ETL
         │  CatalogueValidator                  ▼
         │                            ┌─────────────────┐
         │  Knowledge Base            │  SageMaker      │
         └──► OpenSearch Serverless   │  Feature Store  │
                (product catalogue)   └─────────────────┘
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/orchestrator.py` | Lambda entrypoint — routes requests, validates inputs, calls Bedrock Agent |
| `src/recommendation_model.py` | SageMaker model wrapper — input schema validation, inference, output parsing |
| `src/behaviour_tracker.py` | Publishes behavioural events to Kinesis with schema enforcement |
| `src/guardrails.py` | Hallucination detection — validates agent output against live catalogue |
| `src/audit_logger.py` | Writes model I/O, latency, and decision context to DynamoDB audit table |
| `infra/stack.py` | CDK stack defining all AWS resources |
| `prompts/product_search_v1.2.yaml` | Versioned prompt template for the product search action |
| `tests/test_guardrails.py` | Unit tests for hallucination detection logic |
| `tests/test_recommendation_model.py` | Unit tests for model I/O validation |

---

## Setup

```bash
pip install -r requirements.txt
# Run unit tests with mocked AWS services (moto)
python -m pytest tests/ -v

# Deploy to AWS (requires configured credentials)
cd infra && cdk deploy LegoRecommendationStack
```

---

## Governance Highlights

- **Input validation**: every request is schema-validated before reaching the model (Pydantic models)
- **Output validation**: agent responses are cross-checked against the DynamoDB product catalogue — any product code not found triggers a fallback, never a hallucinated recommendation
- **Audit trail**: every inference is logged with request ID, input hash, output, latency, and model version
- **Prompt versioning**: prompt templates are stored in S3 under `prompts/{name}/v{major}.{minor}.yaml` and referenced by version in code — no inline strings in production
