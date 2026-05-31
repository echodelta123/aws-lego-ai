# AWS AI Application Developer — Portfolio

> **Four production-grade projects demonstrating AWS AI/ML integration, agentic frameworks, ML monitoring, and governed deployment pipelines.**
> Built to show real engineering depth across the AWS AI stack — from Bedrock Agents and LLM integration through to MLOps, drift detection, and enterprise-grade governance.

---

## Why This Portfolio

Hiring managers reading for this role care about one thing above everything else: **can you move AI from proof-of-concept into production, safely, in a complex enterprise environment?**  

Every project here is designed to show that — not just "I called an API", but:
- How model inputs/outputs are validated and logged
- How prompts are versioned and governed
- How drift is detected before it causes business harm
- How AI artefacts flow through a CI/CD pipeline with approval gates
- How hallucinations and high-risk decisions are handled at runtime

---

## Projects at a Glance

| # | Project | Core AWS Services | What It Demonstrates |
|---|---------|-------------------|----------------------|
| 1 | [🧱 LEGO AI Recommendation & Behaviour Engine](#project-1) | Bedrock, SageMaker, Kinesis, DynamoDB, Lambda | LLM integration, agentic product search, customer behaviour, real-time personalisation |
| 2 | [🤖 Agentic Enterprise Assistant](#project-2) | Bedrock Agents, Knowledge Bases, Lambda, S3 | Agentic AI, RAG, hallucination handling, error recovery, prompt governance |
| 3 | [📊 ML Monitoring & Governance Framework](#project-3) | SageMaker Model Monitor, CloudWatch, SNS, Glue | Drift detection, bias checks, model health metrics, prompt versioning |
| 4 | [🚀 Production ML Pipeline (MLOps)](#project-4) | CodePipeline, SageMaker Pipelines, ECR, CDK | CI/CD for ML, model registry, approval gates, SDLC traceability |

---

## Project 1

### 🧱 LEGO AI Recommendation & Customer Behaviour Engine

**Business framing:** LEGO's global e-commerce platform serves millions of customers. This project shows how AWS AI services can deliver real-time, personalised product recommendations while analysing customer behaviour patterns — all in a governed, production-ready architecture.

**Why it matters for this role:** Demonstrates LLM integration into an existing enterprise system, data pipeline design, and agentic natural-language product search — exactly the pattern needed when embedding AI into complex, live production environments.

📁 [`projects/01-lego-recommendation-engine/`](projects/01-lego-recommendation-engine/README.md)

**Key capabilities:**
- **Agentic product search** — Bedrock (Claude 3) agent interprets natural-language queries ("Lego sets good for a 10-year-old who loves space") and calls SageMaker endpoints for ranked recommendations
- **Collaborative filtering model** on SageMaker with real-time inference endpoint
- **Behavioural event streaming** via Kinesis Data Streams → Kinesis Firehose → S3 → Glue → SageMaker Feature Store
- **Hallucination guardrails** — structured output validation ensures the agent never recommends a product that doesn't exist in the catalogue
- **Model input/output logging** with full lineage to DynamoDB audit table

**Architecture highlights:**
```
Customer Request
      │
      ▼
API Gateway → Lambda (Orchestrator)
      │
      ├─► Bedrock Agent (Claude 3 Sonnet)
      │        │
      │        ├─► Action Group: ProductSearch → SageMaker Endpoint
      │        ├─► Action Group: BehaviourLookup → DynamoDB
      │        └─► Knowledge Base (product catalogue) → OpenSearch Serverless
      │
      └─► Kinesis Data Stream (behaviour events)
               │
               ▼
         Firehose → S3 → Glue ETL → SageMaker Feature Store
```

---

## Project 2

### 🤖 Agentic Enterprise Assistant with Prompt Governance

**Business framing:** An internal AI assistant for a large enterprise that answers questions about internal knowledge bases, triggers workflows, and escalates edge cases — with a full prompt governance layer so every interaction is auditable.

**Why it matters for this role:** Shows mastery of the hardest parts of production agentic AI — hallucination detection, error recovery, high-risk decision boundaries, and the prompt governance structures (versioning, constraints, evaluation criteria) that regulators and enterprise risk teams demand.

📁 [`projects/02-agentic-enterprise-assistant/`](projects/02-agentic-enterprise-assistant/README.md)

**Key capabilities:**
- **Bedrock Agents** with multi-step reasoning and custom action groups
- **Retrieval-Augmented Generation (RAG)** via Bedrock Knowledge Bases backed by OpenSearch Serverless
- **Prompt governance registry** — every prompt template is versioned in S3, tested against golden-set evaluations before promotion, and immutable once deployed
- **Hallucination detection** — response confidence scoring with automatic fallback to human escalation below a configurable threshold
- **Error recovery patterns** — retry logic, graceful degradation, dead-letter queues for failed agent invocations
- **High-risk decision boundaries** — keyword/intent classifier prevents the agent acting on requests in defined high-risk categories without human-in-the-loop approval

---

## Project 3

### 📊 ML Monitoring & Governance Framework

**Business framing:** Once models are in production, the real work begins. This framework provides continuous monitoring of model health, data drift, and output quality — with automated alerting and a prompt versioning system built for enterprise governance requirements.

**Why it matters for this role:** Drift detection, model health metrics, and bias checking are explicitly called out in the job description. This project shows those skills concretely, along with the documentation and audit trail that enterprise governance programmes require.

📁 [`projects/03-ml-monitoring-governance/`](projects/03-ml-monitoring-governance/README.md)

**Key capabilities:**
- **SageMaker Model Monitor** scheduled jobs: data quality, model quality, bias drift, feature attribution drift
- **Custom CloudWatch dashboard** aggregating model health KPIs into a single operational view
- **Automated alerting** — SNS topics with Lambda-based enrichment send context-aware alerts to Slack/PagerDuty when drift thresholds breach
- **Prompt versioning system** — Git-backed prompt registry with semantic versioning, automated regression tests (BLEU/ROUGE scoring + human-eval rubrics), and promotion workflow
- **Bias evaluation pipeline** — SageMaker Clarify scheduled to re-evaluate fairness metrics weekly against production traffic
- **Model card generator** — auto-produces standardised model cards (intended use, evaluation results, limitations, monitoring contacts) for every deployed model version

---

## Project 4

### 🚀 Production ML Pipeline — MLOps & SDLC Integration

**Business framing:** This infrastructure project shows how ML model artefacts are built, tested, and deployed with the same rigour as application code — integrated into the existing SDLC toolchain with full audit trails and approval gates.

**Why it matters for this role:** The job description specifically calls out DevOps integration of model artefacts, SDLC traceability, and transitioning from PoC to production. This project is the direct answer to that requirement.

📁 [`projects/04-production-ml-pipeline/`](projects/04-production-ml-pipeline/README.md)

**Key capabilities:**
- **SageMaker Pipelines** for model training, evaluation, and registration — parameterised, reproducible, version-controlled
- **AWS CodePipeline** integration — model training triggered by data changes (S3 event) or code changes (CodeCommit), with unit tests, integration tests, and a manual approval gate before production deployment
- **SageMaker Model Registry** — all models registered with metadata (training data version, evaluation metrics, approval status); deployment blocked unless approval status is `Approved`
- **CDK infrastructure-as-code** for the full pipeline stack — reproducible, environment-specific, diff-able
- **Canary / Blue-Green deployment** — new model version receives 10% traffic; CloudWatch alarm auto-rolls back if error rate exceeds threshold within 30 minutes
- **SDLC traceability matrix** — every model deployment links back to the Jira ticket, Git commit, data version, and evaluation report that approved it

---

## Technical Stack Summary

| Layer | Services / Tools |
|-------|-----------------|
| **AI/LLM** | Amazon Bedrock (Claude 3 Sonnet/Haiku), Bedrock Agents, Bedrock Knowledge Bases |
| **ML Platform** | SageMaker (Training, Endpoints, Pipelines, Feature Store, Model Monitor, Clarify) |
| **Data** | Kinesis Data Streams, Kinesis Firehose, AWS Glue, S3, DynamoDB |
| **Compute/API** | Lambda, API Gateway, ECS Fargate |
| **Search** | OpenSearch Serverless |
| **DevOps/CI-CD** | CodePipeline, CodeBuild, ECR, CDK (Python) |
| **Observability** | CloudWatch, SNS, X-Ray |
| **Governance** | SageMaker Model Registry, S3 versioning, IAM least-privilege, AWS Config |
| **IaC** | AWS CDK (Python) |
| **Language** | Python 3.11 |

---

## Governance & Safety Philosophy

Across all four projects, the same principles apply:

1. **No model ships without an evaluation gate** — automated metrics + human sign-off
2. **Every prompt is versioned and tested** — no ad-hoc prompt changes in production
3. **All model inputs and outputs are logged** — with PII redaction before storage
4. **Drift alerts before business impact** — monitoring is proactive, not reactive
5. **High-risk decisions require human approval** — the agent knows its boundaries
6. **Infrastructure is code** — every environment is reproducible from a CDK stack

---

## 💬 Key Talking Points (Interview-Ready)

These are the high-signal points that demonstrate production engineering maturity — not just "I used the service", but *how* and *why*:

### 1. End-to-End AI Lifecycle Ownership
> "I've built systems that cover the full AI lifecycle — from data ingestion and model training, through real-time inference and agentic orchestration, all the way to production monitoring and automated rollback. This isn't a collection of tutorials; it's an integrated production stack."

### 2. Responsible AI by Design
> "Every project embeds governance from day one — prompt versioning, hallucination detection, bias evaluation, human-in-the-loop gates. I treat AI safety as a first-class architectural concern, not an afterthought."

### 3. Bridging PoC → Production
> "The hardest engineering problem in AI isn't calling the model — it's making it production-ready. I've built the CI/CD pipelines, canary deployments, drift detection, and approval workflows that let AI ship safely at scale."

### 4. Agentic AI with Guardrails
> "I've implemented multi-step reasoning agents that know their own boundaries — they escalate high-risk decisions, validate outputs against ground truth, and gracefully degrade when confidence is low."

### 5. Enterprise-Grade Observability
> "My monitoring isn't just CloudWatch dashboards. It's proactive drift detection, automated bias re-evaluation, context-aware alerting, and full input/output audit trails with PII redaction."

---

## 🏗️ Design Decisions & Trade-Offs

| Decision | Rationale | Trade-Off Accepted |
|----------|-----------|-------------------|
| **Bedrock over self-hosted LLMs** | Managed scaling, no GPU infra to maintain, SOC2/HIPAA compliance inherited from AWS | Less control over model weights; cost scales with token volume rather than fixed compute |
| **SageMaker Pipelines over Airflow/Kubeflow** | Native AWS integration, built-in model registry, no separate orchestration infra | Vendor lock-in to AWS; less portable than Kubeflow if multi-cloud is needed |
| **OpenSearch Serverless for RAG** | Zero-ops vector store, automatic scaling, tight Bedrock Knowledge Base integration | Higher per-query cost at scale vs. self-managed OpenSearch; less tuning control |
| **CDK (Python) over Terraform** | Same language as ML code (Python), type-safe constructs, AWS-native L2/L3 abstractions | Smaller community than Terraform; harder to go multi-cloud later |
| **Kinesis over Kafka (MSK)** | Fully serverless, simpler operational model for event streaming at moderate scale | Lower throughput ceiling; less ecosystem tooling than Kafka |
| **Canary deployment over shadow mode** | Real user validation of new model; catches production-only edge cases | Risk of degraded UX for canary traffic if model underperforms |
| **Prompt registry in S3 (versioned) over database** | Immutable versions via S3 versioning, easy IAM-based access control, audit trail built-in | Less queryable than a database; requires wrapper tooling for search/compare |
| **Human-in-the-loop for high-risk vs. full automation** | Regulatory compliance, reduced blast radius, builds trust with stakeholders | Slower response time for flagged interactions; requires on-call human reviewers |

### Decisions I'd Make Differently at Scale

- **At >1M daily inferences:** Move from Lambda-based orchestration to ECS Fargate for sustained compute, reducing cold-start latency
- **At multi-region:** Introduce DynamoDB Global Tables and cross-region SageMaker endpoints with Route 53 failover
- **At multi-model serving:** Adopt SageMaker Multi-Model Endpoints or inference components to consolidate GPU resources
- **If going multi-cloud:** Replace CDK with Terraform, replace Kinesis with Confluent Kafka, and abstract the ML platform behind a Kubeflow/MLflow layer

---

## 📈 Market Relevance & Industry Alignment

This portfolio directly maps to the capabilities most in-demand across AI/ML engineering roles in 2024–2025:

| Industry Trend | How This Portfolio Demonstrates It |
|---------------|-----------------------------------|
| **Agentic AI adoption** (Gartner Top 10 2025) | Project 2 implements production-ready agents with reasoning, tool use, and guardrails |
| **AI Governance & Responsible AI** (EU AI Act, NIST AI RMF) | Prompt versioning, bias monitoring, model cards, human-in-the-loop — across all projects |
| **MLOps maturity** (ML Engineering > Data Science) | Project 4 shows full CI/CD for ML with approval gates, canary deploys, and traceability |
| **RAG as enterprise standard** | Knowledge Base integration with hallucination detection and structured output validation |
| **Real-time personalisation** (recommender systems) | Project 1 combines collaborative filtering with LLM-powered natural language search |
| **Drift & model degradation** (operational ML) | Project 3 provides continuous monitoring with proactive alerting before business impact |
| **Infrastructure as Code for AI** | Every project is reproducible via CDK — no ClickOps, no snowflake environments |
| **Cost-aware architecture** | Serverless-first design (Lambda, Kinesis, Bedrock) minimises idle cost; scales to zero |

### Certifications & Frameworks Alignment

This work demonstrates competencies aligned with:
- **AWS Certified Machine Learning — Specialty** domain coverage
- **AWS Well-Architected Framework (ML Lens)** — operational excellence, security, reliability, performance, cost optimisation
- **NIST AI Risk Management Framework** — governance, mapping, measurement, management
- **Google's MLOps Maturity Model** — Level 2 (automated training + automated deployment with monitoring)

---

## 🎯 What Sets This Apart

| What Most Portfolios Show | What This Portfolio Shows |
|--------------------------|--------------------------|
| Jupyter notebooks with model training | Full production deployment with CI/CD and rollback |
| "I called the Bedrock API" | Agentic orchestration with error recovery and hallucination handling |
| Static model accuracy metrics | Continuous drift detection with automated re-evaluation |
| README with a diagram | Versioned prompts, model cards, bias reports, and audit trails |
| Single-service demos | Multi-service architectures with event-driven data pipelines |
| No governance story | Enterprise-grade governance baked into every layer |

---

## Running the Projects Locally

Each project includes a `README.md` with prerequisites, setup steps, and a local development mode using LocalStack or moto for AWS service mocking.

```bash
# Prerequisites
python 3.11+
aws cli v2 configured
node 18+ (for CDK)
docker (for local testing)

# Quick start — Project 1
cd projects/01-lego-recommendation-engine
pip install -r requirements.txt
python -m pytest tests/ -v
```

---

*All projects use fictional business data. No real customer PII is included anywhere in this repository.*
