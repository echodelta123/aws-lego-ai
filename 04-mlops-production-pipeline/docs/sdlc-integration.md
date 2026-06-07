# SDLC Integration Guide

## How This Pipeline Integrates With an Existing Enterprise SDLC

This document explains how the ML production pipeline fits into a typical enterprise software delivery lifecycle, making it easy to understand for architects, delivery managers, and governance teams who may not be ML specialists.

---

## The Problem It Solves

Traditional enterprise SDLC tooling (Jira, Git, CodePipeline, testing gates, change management) works well for application code.  ML introduces new artefacts — trained model binaries, training datasets, evaluation reports, prompt templates — that fall outside this tooling without deliberate integration.

This pipeline closes that gap: **every ML model version is treated as a versioned, tested, approved software artefact**, no different from an application release.

---

## Integration Points

### 1. Jira / Work Management
- Each pipeline execution accepts a Jira ticket ID as a required parameter
- The ticket ID is written to the traceability record and the model registry
- Compliance teams can query "which Jira ticket delivered model version X?" in seconds

### 2. Git
- Model training code, evaluation scripts, and CDK infrastructure are all in the same Git repo
- Commits trigger CodePipeline via a CodeCommit event rule
- The commit SHA is embedded in the trained model artefact tags and traceability record
- `git blame` on a training script tells you which deployment it affected

### 3. Change Management (CAB)
- The manual approval gate in CodePipeline maps directly to a Change Advisory Board review
- The approval request email includes: evaluation metrics, model card link, drift analysis
- Approved deployments generate an immutable record with approver name + timestamp
- Emergency rollback is a single CodePipeline re-run to the previous approved config

### 4. Testing Gates

| Gate | What It Checks | Blocks Deployment If... |
|------|----------------|------------------------|
| Unit tests (CodeBuild) | Model training code, preprocessing logic | Any test fails |
| Data quality (Great Expectations) | Input data schema, null rates, ranges | >2% violations |
| Model evaluation (SageMaker) | Accuracy, F1, AUC vs. baseline | Below minimum threshold |
| Bias check (SageMaker Clarify) | Disparate impact, equal opportunity | DI outside 0.8–1.25 |
| Canary monitoring | Live error rate on 10% traffic | >10 errors in 15 min window |

### 5. Operational Handover
- Every deployed model version has a model card with monitoring contacts
- The CloudWatch dashboard is linked from the model card
- On-call runbooks reference the traceability table for root-cause queries
- Rollback procedure is documented and tested — it takes under 5 minutes

---

## Deployment Lifecycle State Machine

```
DataChange / CodeChange
        │
        ▼
  Build & Unit Test ──FAIL──► Pipeline halted, Jira ticket updated
        │ PASS
        ▼
  Train & Evaluate ──FAIL (metrics below threshold)──► Pipeline halted
        │ PASS
        ▼
  PendingManualApproval
        │
        ├── APPROVE ──► Canary Deploy (10% traffic)
        │                    │
        │                    ├── Alarm OK (30 min) ──► Full traffic shift
        │                    │                              │
        │                    │                        Traceability record written
        │                    │
        │                    └── Alarm ALARM ──► Auto-rollback
        │
        └── REJECT ──► Pipeline halted, previous version stays live
```
