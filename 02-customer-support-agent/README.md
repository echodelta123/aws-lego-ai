# Project 2: Customer Support Guardrail Layer

## Production Agentic Architecture

This project implements a conversational customer support built on **Amazon Bedrock Agents** that answers questions over enterprise knowledge bases (like LEGO policies and instructions).

The system is designed with guardrails and patterns:
- **Hallucination Mitigation** — Post-response confidence scoring with automated escalation to human queues when confidence is low.
- **Pre-Execution Guardrails** — Dual-engine intent risk classifier executing risk-level triage before agent invocation to block prompt injection or sensitive actions.
- **Immutable Prompt Governance** — S3-based prompt templates versioned via semantically-controlled releases and checked against golden-set regression test suites.
- **Fault-Tolerant Pipelines** — Resilient workflow execution featuring dead-letter queue (DLQ) support and exponential-backoff retries.
- **Ecosystem Integration**: Shares common schema and DynamoDB logging with the Product Recommendation engine (Project 1), and the SageMaker-backed monitoring and model governance workflows in Project 3/4.
- **Prompt Verification**: Prompt changes run through the automated golden-set CI/CD test runner defined in the [ML Model Monitoring & Governance Framework (Project 3)](../03-ml-model-monitoring/README.md) before publishing.

---

## Architecture

```
User Query
    │
    ▼
API Gateway ──► Lambda Orchestrator
                    │
                    ├─► Intent Risk Classifier (Lambda)
                    │       │
                    │       ├── LOW RISK ──► Bedrock Agent (Claude 3)
                    │       │                   │
                    │       │                   ├── Action: KnowledgeBaseQuery
                    │       │                   │       └── Bedrock Knowledge Base
                    │       │                   │           └── OpenSearch Serverless
                    │       │                   │
                    │       │                   ├── Action: WorkflowTrigger
                    │       │                   │       └── Step Functions
                    │       │                   │
                    │       │                   └── Action: RecordDecision
                    │       │                           └── DynamoDB (decision log)
                    │       │
                    │       └── HIGH RISK ──► Human Approval Queue (SQS)
                    │                           └── SNS Notification
                    │
                    └─► Confidence Scorer
                            │
                            ├── CONFIDENCE >= 0.75 ──► Return response
                            └── CONFIDENCE < 0.75  ──► Escalate to human
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/agent_orchestrator.py` | Main Lambda — orchestrates intent classification, agent invocation, confidence scoring |
| `src/intent_classifier.py` | Risk-level classification before any agent action |
| `src/confidence_scorer.py` | Post-response confidence scoring using a secondary Bedrock call |
| `src/error_recovery.py` | Retry with exponential backoff; DLQ publishing for unrecoverable failures |
| `src/decision_logger.py` | Immutable audit log for every agent decision and action taken |
| `governance/prompt_registry.py` | Loads versioned prompt templates from S3; validates against golden test suite |
| `governance/evaluate_prompt.py` | CI-runnable script: runs a prompt version against its golden tests |
| `prompts/enterprise_assistant_v2.1.yaml` | Current production prompt template |
| `tests/test_confidence_scorer.py` | Unit tests for confidence scoring and escalation logic |
| `tests/test_intent_classifier.py` | Unit tests covering all risk boundary cases |

---

## Governance Model

### Prompt Lifecycle

```
Draft (local YAML)
      │
      ▼
evaluate_prompt.py ──► Run golden tests ──► FAIL? ──► Back to draft
      │ PASS
      ▼
Pull request review by AI governance lead
      │ Approved
      ▼
Upload to S3: prompts/{name}/v{major}.{minor}.yaml
      │
      ▼
Semantic version pinned in application config
      │
      ▼
Production — IMMUTABLE (S3 versioning, no delete)
```

### Risk Boundaries

| Risk Level | Criteria | Action |
|------------|----------|--------|
| LOW | Information retrieval, summarisation | Agent proceeds autonomously |
| MEDIUM | Data modification, external notification | Agent proceeds, decision logged with enhanced detail |
| HIGH | Financial transactions, system configuration changes, legal decisions | Routed to human approval queue; agent does NOT act |
| BLOCKED | Detected sensitive categories (PII requests, security bypass attempts) | Rejected immediately; security team alerted |

---

## Setup

```bash
pip install -r requirements.txt
python -m pytest tests/ -v

# Validate a prompt template against its golden tests
python governance/evaluate_prompt.py --prompt prompts/enterprise_assistant_v2.1.yaml

# Deploy
cd infra && cdk deploy EnterpriseAssistantStack
```

---

## Infrastructure Cost Optimization & Resource Efficiency

To eliminate baseline compute overhead and optimize resources in non-production environments:
- **Serverless-First Compute & Queues** — API Gateway, Lambda, SQS, and SNS operate fully serverless. During periods of inactivity, non-production environments scale to zero, resulting in **$0.00/month** compute fees.
- **Knowledge Base Fallback Index** — In development profiles, active Amazon OpenSearch Serverless clusters (~$140/month baseline) are bypassed in favor of local, lightweight vector indices (FAISS/SQLite) to ensure zero active infrastructure overhead.
- **Observability Profile Integration** — Request traces and latency metadata are pushed to hosted observability platforms (Langfuse Cloud) using standard free-tier quotas, eliminating the need to maintain persistent telemetry instances in development environments.
