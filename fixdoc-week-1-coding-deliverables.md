# FixDoc – Week 1 Coding Deliverables
## Objective: Turn FixDoc into a CI-Native Terraform Risk Engine

By the end of Week 1, FixDoc should be able to:

- Parse Terraform plan JSON
- Compute impact (blast radius lite)
- Score risk deterministically
- Output structured JSON for CI
- Fail pipelines based on configurable thresholds
- Demonstrate CI usage in a real workflow

This document defines the exact coding deliverables required.

---

# 1️⃣ Impact Preview Lite (Blast Radius v1)

## Goal
Add dependency-based impact analysis to `fixdoc analyze`.

## CLI Interface

```bash
fixdoc analyze plan.json --impact
fixdoc analyze plan.json --impact --depth 2
```

## Required Functionality

### 1. Parse Terraform Plan JSON

Extract:
- `resource_changes`
- `change.actions`
- resource `address`
- dependency references (from configuration or explicit `depends_on`)

### 2. Identify Changed Resources (L0)

Build list:
```python
changed_resources = [
    {
        "address": "aws_iam_role.app",
        "actions": ["delete"]
    }
]
```

### 3. Build Dependency Graph

Construct graph structure:

```python
graph = {
    "aws_iam_role.app": ["aws_iam_policy_attachment.app"],
    "aws_iam_policy_attachment.app": ["lambda_function.api"]
}
```

Graph must support:
- Depth-limited traversal
- Reverse dependency lookup (who depends on X)

### 4. Traverse Impact (Bounded BFS)

Default depth: 2

Output:

```
Changed Resources (L0):
- aws_iam_role.app (delete)

Impacted (L1):
- aws_iam_policy_attachment.app

Impacted (L2):
- lambda_function.api

Total impacted: 3
```

---

# 2️⃣ Risk Scoring Engine

## Goal
Deterministic risk score from 0–100 based on signals.

## CLI Interface

```bash
fixdoc analyze plan.json --impact --risk
```

## Risk Signals (Required for Week 1)

### Signal A – Destructive Actions
- delete → +30
- replace → +20

### Signal B – Sensitive Resource Types
Match by resource type string:
- iam_role
- iam_policy
- role_assignment
- key_vault
- security_group
- network_security_group
- firewall

Score: +20

### Signal C – Historical Fix Match
If changed resource type matches tags in fix history:
+15 per match

### Signal D – Blast Radius Size
- 0–2 impacted → +0
- 3–5 impacted → +10
- 6+ impacted → +20

## Output Format

```
Risk Score: 72 / 100 (HIGH)

Signals:
- destructive_action
- iam_resource
- blast_radius_large
- fix_history_match (2)

Recommendation:
Review IAM changes carefully before apply.
```

---

# 3️⃣ CI-Friendly Output

## CLI Flags (Required)

```bash
--format json
--exit-on high
--exit-on medium
```

## JSON Output Example

```json
{
  "risk_score": 72,
  "risk_level": "high",
  "changed_resources": 1,
  "impacted_resources": 7,
  "fix_matches": 2,
  "signals": [
    "delete_action",
    "iam_resource",
    "fix_history_match"
  ]
}
```

## Exit Code Behavior

If:

```bash
fixdoc analyze plan.json --impact --exit-on high
```

And risk >= high threshold → exit(1)

Else → exit(0)

---

# 4️⃣ Threshold Configuration

Hardcode for Week 1:

- 0–39 → low
- 40–69 → medium
- 70–100 → high

Future: move to config file.

---

# 5️⃣ GitHub Actions Example (Must Ship)

Add to documentation:

```yaml
name: Terraform Risk Analysis

on: [pull_request]

jobs:
  risk-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2

      - name: Terraform Plan
        run: |
          terraform init
          terraform plan -out=plan.tfplan

      - name: Analyze Risk
        run: |
          terraform show -json plan.tfplan > plan.json
          fixdoc analyze plan.json --impact --exit-on high
```

---

# Week 1 Success Criteria

By end of Week 1, you can say:

> FixDoc scores Terraform plan risk based on destructive actions, IAM changes, dependency impact, and historical failures — and can block high-risk PRs in CI.

If you can confidently demonstrate that in under 3 minutes, Week 1 is complete.
