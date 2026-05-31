# Project 2: Agentic Enterprise Assistant with Prompt Governance

## What This Project Shows

A production-grade internal AI assistant built on **AWS Bedrock Agents** that answers questions over enterprise knowledge bases, triggers downstream workflows, and enforces strict governance over every prompt interaction.

This project directly addresses the hardest parts of the job description:

- **Hallucination handling** — confidence scoring + automatic human escalation
- **Error recovery** — retry logic, dead-letter queues, graceful degradation
- **High-risk decision boundaries** — intent classifier prevents unsafe agent actions
- **Prompt governance** — every template versioned, tested, and immutable in production
- **Agentic AI frameworks** — multi-step reasoning with controlled action execution

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
