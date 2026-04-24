# test_terraform — Local Terraform Sandbox for fixdoc

Run real `terraform apply` against LocalStack (mock AWS on Docker) to generate genuine Terraform errors for testing `fixdoc watch` and `fixdoc blast-radius`.

## Prerequisites

- Docker
- Terraform CLI
- fixdoc installed (`pip install -e .` from repo root)

## Architectures

There are three architectures, each in its own directory:

| Directory | Description | Resources | Blast Radius Focus |
|-----------|-------------|-----------|-------------------|
| `.` (root) | Multi-tier web app | 15 — VPC, EC2, Lambda, S3, RDS, ALB | General purpose |
| `microservices/` | Event-driven microservices | ~30 — shared IAM role, 4 Lambdas, SQS/SNS fan-out, DynamoDB, Secrets Manager | **IAM cascade** — one shared role change propagates to all services |
| `network_mesh/` | Multi-VPC network mesh | ~45 — 3 VPCs, peering, layered SGs, NACLs, route tables, RDS, ALB | **Network control points** — SG/NACL/route changes have wide blast radius |

## Quick Start

```bash
# 1. Start LocalStack (shared by all architectures)
cd test_terraform
docker compose up -d

# 2. Pick an architecture and init
terraform init                              # root (web app)
terraform -chdir=microservices init         # microservices
terraform -chdir=network_mesh init          # network mesh

# 3. Apply and capture errors with fixdoc
fixdoc watch -- terraform apply -auto-approve
fixdoc watch -- terraform -chdir=microservices apply -auto-approve
fixdoc watch -- terraform -chdir=network_mesh apply -auto-approve

# 4. Test blast radius (generate plan JSON first)
terraform plan -out=plan.bin && terraform show -json plan.bin > plan.json
fixdoc blast-radius plan.json

# 5. Clean up
terraform destroy -auto-approve
docker compose down
```

## Architecture Details

### Root: Multi-Tier Web App (`main.tf`)

Classic 3-tier: VPC → subnets → security groups → EC2/Lambda/RDS/ALB. Good for general error capture testing.

### Microservices (`microservices/main.tf`)

Event-driven pipeline:

```
SQS (orders) → Lambda (order-processor) → DynamoDB (orders)
                                        → SNS (events) → SQS (payments)  → Lambda (payment-processor)
                                                       → SQS (notifications) → Lambda (notifier)
                                                       → SQS (archive)    → Lambda (archiver) → S3
```

All 4 Lambdas share **one IAM role** with 3 policy attachments. Changing the role or any policy cascades to every service. Also uses Secrets Manager for DB creds (Lambda reads at runtime). Great for testing:
- High blast radius from IAM changes
- Deep dependency chains (SNS → SQS → Lambda → DynamoDB)
- DLQ alarms (CloudWatch)

### Network Mesh (`network_mesh/main.tf`)

Three VPCs connected by peering:

```
Production VPC (10.0.0.0/16) ←→ Shared Services VPC (10.2.0.0/16)
Staging VPC (10.1.0.0/16)    ←→ Shared Services VPC (10.2.0.0/16)
```

Layered security groups with cross-references:
```
bastion-sg → app-sg → db-sg
             app-sg → cache-sg
alb-sg     → app-sg
```

NACLs on public/private subnets, route tables with peering routes. Great for testing:
- Wide blast radius from network control points (SGs, NACLs, route tables)
- VPC peering changes severing cross-VPC communication
- Layered SG dependencies (changing bastion-sg affects app-sg → db-sg → cache-sg)

## LocalStack Coverage

LocalStack Community (free) fully supports: S3, IAM, Lambda, EC2, SQS, SNS, DynamoDB, CloudWatch, STS, Secrets Manager, SSM, Route53, CloudFormation.

Some services (RDS, ELB/ALB, ECS) have partial support — they may fail with realistic errors, which is useful for testing fixdoc error capture.

## Notes

- Credentials are dummy values (`test`/`test`) — nothing touches real AWS.
- Missing `.zip` files for Lambda functions will produce real Terraform errors — good for testing fixdoc capture.
- LocalStack data persists in a Docker volume. Use `docker compose down -v` to wipe it.
- All architectures share the same LocalStack instance on `localhost:4566`.
