# FixDoc Scenario Test Runbook

Human-executable checklist for the full scenario matrix. Each scenario
validates a specific `fixdoc watch` or `fixdoc analyze` code path against
LocalStack (or real AWS where noted).

---

## Prerequisites

1. **Docker + LocalStack**
   ```bash
   cd test_terraform/
   docker compose up -d
   # Verify: curl -s http://localhost:4566/_localstack/health | jq .services
   ```

2. **fixdoc installed**
   ```bash
   pip install -e .
   fixdoc --version
   ```

3. **Terraform ≥ 1.5 on PATH**
   ```bash
   terraform version
   ```

4. **Optional: seed your ~/.fixdoc with realistic fixes** (improves tribal
   knowledge checks in scenarios 11, 16, 17)
   ```bash
   fixdoc demo seed
   ```

---

## Run All Scenarios (Automated)

```bash
bash scenarios/run_all.sh
```

This runs all 17 scenarios in order. LocalStack must be running.
Scenario 10 (IAM Cascade Deny) prints a docs-only notice — it requires
real AWS credentials to observe actual AccessDenied errors.

---

## Watch Scenarios (05–10)

### 05: Multi-failure Missing Vars

**What it tests**: `fixdoc watch` capturing 4 "Missing required argument"
errors when two child modules each omit 2 required variables.

**Run**:
```bash
cd scenarios/05-watch-multi-failure-missing-vars
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
fixdoc watch -- terraform apply -auto-approve
```

**Expected**:
- Terraform fails with 4 errors (2 per module)
- Watch auto-defers all 4 error(s) to `.fixdoc-pending`
  Output: `Apply failed. 4 error(s) deferred to pending.`
- Summary card shows deferred resource list, offers `[c] capture one now  [s] skip`
- On the next successful run, watch prompts to document what fixed each error
- To inspect deferred entries at any time: `fixdoc pending`
- To document fixes immediately: `fixdoc resolve`

**Verify**:
```bash
fixdoc pending
```

---

### 06: Invalid Resources

**What it tests**: Two different client-side validation errors at plan time:
- `aws_security_group` with `cidr_blocks = ["10.0.0.0/33"]`
- `aws_iam_role` with `assume_role_policy = "not valid json"`

**Run**:
```bash
cd scenarios/06-watch-invalid-resources
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
fixdoc watch -- terraform apply -auto-approve
```

**Expected**:
- Watch auto-defers all 2 error(s) to `.fixdoc-pending`
  Output: `Apply failed. 2 error(s) deferred to pending.`
- Summary card shows deferred resource list, offers `[c] capture one now  [s] skip`
- 2 distinct entries in `.fixdoc-pending` with different `resource_address` values:
  - `aws_security_group.bad_cidr`
  - `aws_iam_role.bad_policy`
- On the next successful run, watch prompts to document what fixed each error
- To inspect deferred entries at any time: `fixdoc pending`
- To document fixes immediately: `fixdoc resolve`

---

### 07: Parallelism Bomb

**What it tests**: Six S3 buckets created in parallel with the same name.
First succeeds; remaining 5 fail with `BucketAlreadyExists` (LocalStack).

**Run**:
```bash
cd scenarios/07-watch-parallelism-bomb
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
fixdoc watch -- terraform apply -auto-approve -parallelism=10
```

**Expected**:
- Watch auto-defers up to 5 apply-time errors to `.fixdoc-pending`
  Output: `Apply failed. N error(s) deferred to pending.`
- Summary card shows deferred resource list, offers `[c] capture one now  [s] skip`
- Watch handles interleaved error stream without losing messages
- On the next successful run, watch prompts to document what fixed each error
- To inspect deferred entries at any time: `fixdoc pending`
- To document fixes immediately: `fixdoc resolve`

**Cleanup** (if partial state exists):
```bash
terraform destroy -auto-approve
```

---

### 08: Terraform Graph / Language Errors

**What it tests**: Two `variable` declarations with `type = number` but
non-numeric defaults. Both "Invalid default value for variable" errors
surface at module-load time — before any AWS API calls.

**Run**:
```bash
cd scenarios/08-watch-terraform-graph-errors
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
fixdoc watch -- terraform plan
```

**Expected**:
- Watch auto-defers all 2 error(s) to `.fixdoc-pending`
  Output: `Plan failed. 2 error(s) deferred to pending.`
- Summary card shows deferred resource list, offers `[c] capture one now  [s] skip`
- 2 errors: `instance_count` and `bucket_count` type mismatches
- File + line numbers in error messages
- No LocalStack connectivity needed (errors are TF-internal)
- To inspect deferred entries at any time: `fixdoc pending`
- To document fixes immediately: `fixdoc resolve`

---

### 09: Multi-module Same Error

**What it tests**: Two module instances (`module.app_a`, `module.app_b`)
both fail with the same "Invalid CIDR" error but different resource
addresses. Watch should present both as separate captures.

**Run**:
```bash
cd scenarios/09-watch-multi-module-same-error
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
fixdoc watch -- terraform apply -auto-approve
```

**Expected**:
- Watch auto-defers all 2 error(s) to `.fixdoc-pending`
  Output: `Apply failed. 2 error(s) deferred to pending.`
- Summary card shows deferred resource list, offers `[c] capture one now  [s] skip`
- 2 entries in `.fixdoc-pending` with distinct `resource_address` values:
  - `module.app_a.aws_security_group.main`
  - `module.app_b.aws_security_group.main`
- Both appear separately (not collapsed into one)
- On the next successful run, watch prompts to document what fixed each error
- To inspect deferred entries at any time: `fixdoc pending`
- To document fixes immediately: `fixdoc resolve`

---

### 10: IAM Cascade Deny [Real AWS Only]

**What it tests**: After attaching an explicit Deny IAM policy to the
provisioner role, all subsequent apply operations fail with `AccessDenied`.

**Note**: LocalStack Community does not enforce IAM permissions. Run this
scenario against real AWS with appropriate credentials.

**Setup** (real AWS):
```bash
# Set real AWS credentials
export AWS_PROFILE=your-profile
# Edit providers.tf to remove LocalStack endpoint overrides
# Then apply baseline:
cd scenarios/10-watch-iam-cascade-deny
terraform init
terraform apply -auto-approve
# This creates the deny policy and attaches it to the provisioner role.
# On re-apply, all resources fail with AccessDenied.
fixdoc watch -- terraform apply -auto-approve
```

**Expected errors** (see `fixtures/expected_errors.txt`):
- `ec2:RunInstances → UnauthorizedOperation`
- `iam:CreateRole → AccessDenied`
- `s3:CreateBucket → AccessDenied`
- `ec2:CreateSubnet → UnauthorizedOperation`

**Cleanup**:
```bash
# Remove the deny policy attachment first, then destroy
terraform destroy -auto-approve
```

---

### Quota / Throttling [Real AWS Only]

Not implemented as a LocalStack config. To test watch with throttling errors:

```bash
# Trigger ThrottlingException by hammering the API:
fixdoc watch -- aws ec2 describe-instances  # loop externally
```

Expected: watch captures `ThrottlingException: Request rate exceeded` and
routes to the TerraformParser or generic capture.

---

### STS Token Expiry [Real AWS Only]

Not implemented. To test:

```bash
# Use a short-lived STS token, let it expire mid-apply:
fixdoc watch -- terraform apply -auto-approve
# Expected: ExpiredTokenException: Request has expired
```

---

## Analyze Scenarios (11–17)

### 11: Create-Only Non-Boundary

**What it tests**: Greenfield plan with only non-boundary creates (VPC,
subnets, S3 buckets, EC2 without SG). Score is LOW (greenfield 0.3x
multiplier). `find_resource_prior_fixes()` surfaces tribal warnings if the
fix DB has relevant records, even without L2 BFS.

**Run**:
```bash
cd scenarios/11-analyze-create-only-non-boundary
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
terraform plan -out=plan.tfplan && terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json
```

**Verify**:
- Score: LOW severity
- No "Control Points" section (no IAM/SG/ACL in plan)
- "Prior Issues for Changed Resources" appears only if fix DB has aws_s3_bucket or aws_instance fixes

---

### 12: IAM Deep Chain

**What it tests**: 4-resource IAM hierarchy. Changing `aws_iam_role.app`
(control point) triggers BFS propagation:
- Depth 1: `aws_iam_instance_profile.app`, `aws_iam_role_policy_attachment.app`
- Depth 2: `aws_instance.app`

**Run**:
```bash
cd scenarios/12-analyze-iam-deep-chain
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
terraform apply -auto-approve -var="policy_mode=baseline"
terraform graph > graph.dot
terraform plan -var="policy_mode=changed" -out=plan.tfplan
terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json --graph graph.dot
```

**Verify**:
- `aws_iam_role.app` listed as control point (category=iam)
- Affected resources include `aws_iam_instance_profile.app` and `aws_instance.app`
- Score: MEDIUM or higher (IAM change with dependent EC2)

**Cleanup**:
```bash
terraform destroy -auto-approve -var="policy_mode=baseline"
```

---

### 13: Replace + Delete Heavy

**What it tests**: Changing VPC CIDR (immutable) forces VPC replace, which
cascades to subnet, SG, and EC2 (all replace). Extra S3 bucket is deleted.
`has_destructive=True` → L2 BFS fires, history matches can populate.

**Run**:
```bash
cd scenarios/13-analyze-replace-delete-heavy
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
terraform apply -auto-approve -var="policy_mode=baseline"
terraform plan -var="policy_mode=changed" -out=plan.tfplan
terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json
```

**Verify**:
- Multiple `replace` actions for VPC, subnet, SG, EC2
- `delete` action for `aws_s3_bucket.extra[0]`
- Score: HIGH or CRITICAL severity
- `has_destructive=True` triggers L2 BFS

**Cleanup**:
```bash
terraform destroy -auto-approve -var="policy_mode=baseline"
```

---

### 14: Bad Plan (auto + manual fixtures)

**What it tests**: Graceful error handling for malformed plan JSON files.

**Auto-run** (via `run_all.sh`): runs valid plan + probes each fixture.

**Manual fixture checks**:
```bash
cd scenarios/14-analyze-bad-plan
export FIXDOC_HOME="$PWD/.fixdoc-test"

# Valid baseline plan
terraform init
terraform plan -out=plan.tfplan && terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json

# Malformed fixtures
fixdoc analyze fixtures/empty.json
# Expected: error about missing resource_changes or empty plan

fixdoc analyze fixtures/invalid.json
# Expected: "Error: Invalid JSON" or similar parse error

fixdoc analyze fixtures/no_changes.json
# Expected: "No changes" or score=0 output
```

---

### 15: No-Op Plan

**What it tests**: Second plan after full apply shows only `no-op` and
`read` actions. `is_actionable_change()` filters all of them, resulting
in score=0 and empty resource_warnings.

**Run**:
```bash
cd scenarios/15-analyze-no-op-plan
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
terraform apply -auto-approve
terraform plan -out=plan.tfplan && terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json
```

**Verify**:
- Score: 0
- Severity: low
- "No actionable changes" or similar message
- No "Prior Issues" section

**Cleanup**:
```bash
terraform destroy -auto-approve
```

---

### 16: Huge Plan — Performance Check

**What it tests**: 250-resource plan (50 × 5 types). Verifies
`find_by_resource_type` deduplication (5 unique types = 5 DB calls) and
end-to-end performance.

**Run**:
```bash
cd scenarios/16-analyze-huge-plan
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
terraform plan -out=plan.tfplan && terraform show -json plan.tfplan > plan.json

# Performance check — should complete in < 2s
time fixdoc analyze plan.json --max-warnings 10
```

**Verify**:
- Command completes in under 2 seconds
- 5 resource types listed in output (aws_s3_bucket, aws_security_group,
  aws_iam_role, aws_iam_role_policy, aws_cloudwatch_log_group)
- Score reflects large number of creates (IAM roles are control points)

---

### 17: Word Boundary Trap (manual seed required)

**What it tests**: Fix DB contains fixes for `aws_s3_bucket_policy` and
`aws_s3_bucket_public_access_block` but NOT `aws_s3_bucket`. The
word-boundary regex `\baws_s3_bucket\b` should not match the longer names.

**Setup** (seed trap fixes):
```bash
export FIXDOC_HOME="$PWD/scenarios/17-analyze-word-boundary-traps/.fixdoc-test"
mkdir -p "$FIXDOC_HOME"

fixdoc capture --issue "aws_s3_bucket_policy permission denied on upload" \
               --resolution "Check bucket policy JSON for s3:PutObject" \
               --tags "s3,policy,permissions"

fixdoc capture --issue "aws_s3_bucket_public_access_block not propagating to objects" \
               --resolution "Wait 30s for eventual consistency; also check object ACLs" \
               --tags "s3,public-access,consistency"
```

**Run**:
```bash
cd scenarios/17-analyze-word-boundary-traps
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init
terraform plan -out=plan.tfplan && terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json
```

**Verify**:
- "Prior Issues for Changed Resources" section is **ABSENT**
- No false-positive match for `aws_s3_bucket` against trap fixes
- Confirms `\b` word boundary prevents `aws_s3_bucket` from matching
  `aws_s3_bucket_policy` or `aws_s3_bucket_public_access_block`

---

## Quick Verification Checklist

```bash
# 1. Full automated run (LocalStack must be running)
bash scenarios/run_all.sh

# 2. Scenario 16 performance spot-check
time fixdoc analyze scenarios/16-analyze-huge-plan/plan.json --max-warnings 10

# 3. Scenario 14 bad-plan fixture spot-checks
fixdoc analyze scenarios/14-analyze-bad-plan/fixtures/invalid.json
fixdoc analyze scenarios/14-analyze-bad-plan/fixtures/no_changes.json

# 4. Unit test suite — no regressions
python3 -m pytest

# 5. Scenario 17 word-boundary check (after manual seed)
#    Expect: no "Prior Issues" section in output
fixdoc analyze scenarios/17-analyze-word-boundary-traps/plan.json

# 6. Watch scenario smoke test (LocalStack must be running)
cd scenarios/06-watch-invalid-resources
export FIXDOC_HOME="$PWD/.fixdoc-test"
terraform init -upgrade -reconfigure
fixdoc watch --no-prompt -- terraform apply -auto-approve || true
cat .fixdoc-pending  # should contain 2 entries
rm -f .fixdoc-pending
```

---

## Scenario Summary Table

| # | Name                        | Type    | Runner                           | Real AWS? |
|---|-----------------------------|---------|----------------------------------|-----------|
| 01 | greenfield                 | analyze | run_plan                         | No        |
| 02 | update-nonboundary         | analyze | run_apply_then_plan_update_nonboundary | No  |
| 03 | boundary-sg-update         | analyze | run_apply_then_plan_sg_update    | No        |
| 04 | iam-boundary-update        | analyze | run_apply_then_plan_update_boundary | No     |
| 05 | watch-multi-failure-missing-vars | watch | run_watch_scenario           | No        |
| 06 | watch-invalid-resources    | watch   | run_watch_scenario               | No        |
| 07 | watch-parallelism-bomb     | watch   | run_watch_scenario               | No        |
| 08 | watch-terraform-graph-errors | watch | run_watch_scenario_plan          | No        |
| 09 | watch-multi-module-same-error | watch | run_watch_scenario              | No        |
| 10 | watch-iam-cascade-deny     | watch   | docs-only                        | **Yes**   |
| 11 | analyze-create-only-non-boundary | analyze | run_plan                  | No        |
| 12 | analyze-iam-deep-chain     | analyze | run_apply_then_plan_update_boundary | No   |
| 13 | analyze-replace-delete-heavy | analyze | run_apply_then_plan_update_boundary | No  |
| 14 | analyze-bad-plan           | analyze | run_analyze_bad_plan             | No        |
| 15 | analyze-no-op-plan         | analyze | run_apply_then_plan_noop         | No        |
| 16 | analyze-huge-plan          | analyze | run_plan                         | No        |
| 17 | analyze-word-boundary-traps | analyze | run_plan (manual seed)          | No        |
| —  | quota/throttling            | watch   | manual only                      | **Yes**   |
| —  | sts-token-expiry            | watch   | manual only                      | **Yes**   |
