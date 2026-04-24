# Scenario 10: IAM Cascade Deny [Real AWS Only]

## What it tests

After attaching an explicit Deny IAM policy to the provisioner role, all
subsequent `terraform apply` operations fail with `AccessDenied` or
`UnauthorizedOperation`. This exercises `fixdoc watch` handling of
cascading permission errors across multiple resource types.

## Why real AWS only

LocalStack Community does not enforce IAM permissions. This scenario
requires real AWS credentials to observe actual `AccessDenied` errors.

## Prerequisites

- Real AWS credentials with permission to create IAM roles and policies
- An AWS account where you can safely create/delete test resources

## Steps

```bash
# 1. Set real AWS credentials
export AWS_PROFILE=your-profile
# or: export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...

cd scenarios/10-watch-iam-cascade-deny

# 2. Initialize
terraform init

# 3. Apply baseline — creates provisioner role + deny policy attachment
terraform apply -auto-approve

# 4. Re-apply — all resources now fail with AccessDenied due to the deny policy
export FIXDOC_HOME="$PWD/.fixdoc-test"
mkdir -p "$FIXDOC_HOME"
fixdoc watch -- terraform apply -auto-approve
```

## Expected behavior

- `fixdoc watch` auto-defers all errors to `.fixdoc-pending`
- Output: `Apply failed. N error(s) deferred to pending.`
- Summary card lists each resource that failed with its error type
- Inspect deferred entries: `fixdoc pending`
- Document what fixed them: `fixdoc resolve`

## Expected error patterns

See `fixtures/expected_errors.txt`:

```
ec2:RunInstances → UnauthorizedOperation
iam:CreateRole → AccessDenied
s3:CreateBucket → AccessDenied
ec2:CreateSubnet → UnauthorizedOperation
```

## Cleanup

```bash
# Remove the deny policy attachment first, then destroy
# (you may need to detach the deny policy manually via the AWS console
#  if the role no longer has permission to modify itself)
aws iam detach-role-policy \
  --role-name fixdoc-watch10-provisioner \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/fixdoc-watch10-deny-all

terraform destroy -auto-approve
rm -rf .fixdoc-test .fixdoc-pending
```
