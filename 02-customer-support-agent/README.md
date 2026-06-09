# Project 2: Customer Support Guardrail Layer

## Overview

This project implements a customer support assistant built on Amazon Bedrock Agents. It answers questions using enterprise knowledge bases such as product documentation and internal policies.

The focus is on making the system safe, predictable, and easy to govern in production.

Key design goals:

* **Reducing hallucinations** — responses are scored after generation, and low-confidence outputs are escalated to human review.
* **Pre-request safety checks** — incoming requests are classified by risk level before the agent runs, helping block unsafe or sensitive actions early.
* **Controlled prompt management** — prompts are versioned in S3 and promoted only after passing regression tests.
* **Reliable execution** — retries, backoff logic, and dead-letter queues are used for failure handling.
* **Shared platform integration** — uses the same logging and schema patterns as Project 1, and integrates with the monitoring and MLOps systems in Projects 3 and 4.
* **Prompt testing pipeline** — changes to prompts must pass automated evaluation before being deployed.

---

## Architecture

```
User Query
    │
    ▼
API Gateway ──► Lambda Orchestrator
                    │
                    ├─► Intent Risk Classifier
                    │
                    ├── LOW RISK ──► Bedrock Agent
                    │                     │
                    │                     ├─► Knowledge Base (OpenSearch)
                    │                     ├─► Step Functions (workflows)
                    │                     └─► DynamoDB (decision logs)
                    │
                    ├── HIGH RISK ──► Human Review Queue (SQS)
                    │                     └─ SNS notification
                    │
                    └─► Confidence Scoring
                            │
                            ├── High confidence → return response
                            └── Low confidence → escalate to human
```

---

## Key Files

| File                                     | Purpose                                           |
| ---------------------------------------- | ------------------------------------------------- |
| `src/agent_orchestrator.py`              | Main Lambda function coordinating the workflow    |
| `src/intent_classifier.py`               | Classifies request risk level before execution    |
| `src/confidence_scorer.py`               | Scores responses and decides whether to escalate  |
| `src/error_recovery.py`                  | Handles retries and sends failures to DLQ         |
| `src/decision_logger.py`                 | Logs all decisions and actions for audit purposes |
| `governance/prompt_registry.py`          | Loads versioned prompts from S3                   |
| `governance/evaluate_prompt.py`          | Runs automated tests on prompt versions           |
| `prompts/enterprise_assistant_v2.1.yaml` | Current production prompt                         |
| `tests/test_confidence_scorer.py`        | Tests for scoring and escalation logic            |
| `tests/test_intent_classifier.py`        | Tests for risk classification                     |

---

## Prompt Lifecycle

```
Local draft (YAML)
      │
      ▼
Run evaluation tests (evaluate_prompt.py)
      │
      ├── Fail → revise prompt
      │
      └── Pass
            │
            ▼
Code review / approval
            │
            ▼
Upload to S3 (versioned)
            │
            ▼
Pinned in production config (immutable)
```

---

## Risk Model

| Level   | What it covers                                 | System behavior            |
| ------- | ---------------------------------------------- | -------------------------- |
| Low     | General questions, summaries                   | Agent responds normally    |
| Medium  | Operational actions or structured workflows    | Allowed, fully logged      |
| High    | Financial, legal, or system-impacting actions  | Sent to human review queue |
| Blocked | Prompt injection, sensitive or unsafe requests | Rejected immediately       |

---

## Setup

```bash
pip install -r requirements.txt
pytest tests/ -v

# Run prompt evaluation
python governance/evaluate_prompt.py --prompt prompts/enterprise_assistant_v2.1.yaml

# Deploy
cd infra && cdk deploy EnterpriseAssistantStack
```

---

## Cost and Resource Design

The system is built to avoid unnecessary baseline costs in development environments:

* **Fully serverless architecture** (Lambda, API Gateway, SQS, SNS) so idle usage costs are near zero.
* **Knowledge base fallback** replaces OpenSearch Serverless in dev with lightweight local vector stores.
* **Observability tools** rely on hosted/free-tier usage rather than dedicated infrastructure in non-prod environments.

---
