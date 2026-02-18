# main.tf — Multi-VPC Network Mesh with Shared Services
# Tests blast radius: many network control points (SGs, NACLs, route tables),
# wide propagation through VPC peering and cross-references, IAM for
# cross-account access patterns.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    ec2            = "http://localhost:4566"
    iam            = "http://localhost:4566"
    lambda         = "http://localhost:4566"
    s3             = "http://localhost:4566"
    sts            = "http://localhost:4566"
    secretsmanager = "http://localhost:4566"
  }
}

# =========================================================================
# VPC: Production
# =========================================================================

resource "aws_vpc" "production" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "production-vpc" }
}

resource "aws_subnet" "prod_public_a" {
  vpc_id                  = aws_vpc.production.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true

  tags = { Name = "prod-public-a" }
}

resource "aws_subnet" "prod_public_b" {
  vpc_id                  = aws_vpc.production.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "us-east-1b"
  map_public_ip_on_launch = true

  tags = { Name = "prod-public-b" }
}

resource "aws_subnet" "prod_private_a" {
  vpc_id            = aws_vpc.production.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "us-east-1a"

  tags = { Name = "prod-private-a" }
}

resource "aws_subnet" "prod_private_b" {
  vpc_id            = aws_vpc.production.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "us-east-1b"

  tags = { Name = "prod-private-b" }
}

resource "aws_internet_gateway" "prod" {
  vpc_id = aws_vpc.production.id

  tags = { Name = "prod-igw" }
}

resource "aws_route_table" "prod_public" {
  vpc_id = aws_vpc.production.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.prod.id
  }

  # Route to shared services VPC via peering
  route {
    cidr_block                = "10.2.0.0/16"
    vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_shared.id
  }

  tags = { Name = "prod-public-rt" }
}

resource "aws_route_table_association" "prod_public_a" {
  subnet_id      = aws_subnet.prod_public_a.id
  route_table_id = aws_route_table.prod_public.id
}

resource "aws_route_table_association" "prod_public_b" {
  subnet_id      = aws_subnet.prod_public_b.id
  route_table_id = aws_route_table.prod_public.id
}

resource "aws_route_table" "prod_private" {
  vpc_id = aws_vpc.production.id

  # Route to shared services VPC via peering
  route {
    cidr_block                = "10.2.0.0/16"
    vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_shared.id
  }

  tags = { Name = "prod-private-rt" }
}

resource "aws_route_table_association" "prod_private_a" {
  subnet_id      = aws_subnet.prod_private_a.id
  route_table_id = aws_route_table.prod_private.id
}

resource "aws_route_table_association" "prod_private_b" {
  subnet_id      = aws_subnet.prod_private_b.id
  route_table_id = aws_route_table.prod_private.id
}

# Production NACLs — blast radius: changing these affects all prod subnets
resource "aws_network_acl" "prod_public" {
  vpc_id     = aws_vpc.production.id
  subnet_ids = [aws_subnet.prod_public_a.id, aws_subnet.prod_public_b.id]

  ingress {
    protocol   = "tcp"
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 80
    to_port    = 80
  }

  ingress {
    protocol   = "tcp"
    rule_no    = 110
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 443
    to_port    = 443
  }

  ingress {
    protocol   = "tcp"
    rule_no    = 200
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 1024
    to_port    = 65535
  }

  egress {
    protocol   = "-1"
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 0
    to_port    = 0
  }

  tags = { Name = "prod-public-nacl" }
}

resource "aws_network_acl" "prod_private" {
  vpc_id     = aws_vpc.production.id
  subnet_ids = [aws_subnet.prod_private_a.id, aws_subnet.prod_private_b.id]

  ingress {
    protocol   = "tcp"
    rule_no    = 100
    action     = "allow"
    cidr_block = "10.0.0.0/16"
    from_port  = 0
    to_port    = 65535
  }

  ingress {
    protocol   = "tcp"
    rule_no    = 110
    action     = "allow"
    cidr_block = "10.2.0.0/16"
    from_port  = 0
    to_port    = 65535
  }

  egress {
    protocol   = "-1"
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 0
    to_port    = 0
  }

  tags = { Name = "prod-private-nacl" }
}

# =========================================================================
# VPC: Staging (mirrors production, peered to shared services)
# =========================================================================

resource "aws_vpc" "staging" {
  cidr_block           = "10.1.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "staging-vpc" }
}

resource "aws_subnet" "staging_public" {
  vpc_id                  = aws_vpc.staging.id
  cidr_block              = "10.1.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true

  tags = { Name = "staging-public" }
}

resource "aws_subnet" "staging_private" {
  vpc_id            = aws_vpc.staging.id
  cidr_block        = "10.1.10.0/24"
  availability_zone = "us-east-1a"

  tags = { Name = "staging-private" }
}

resource "aws_internet_gateway" "staging" {
  vpc_id = aws_vpc.staging.id

  tags = { Name = "staging-igw" }
}

resource "aws_route_table" "staging_public" {
  vpc_id = aws_vpc.staging.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.staging.id
  }

  route {
    cidr_block                = "10.2.0.0/16"
    vpc_peering_connection_id = aws_vpc_peering_connection.staging_to_shared.id
  }

  tags = { Name = "staging-public-rt" }
}

resource "aws_route_table_association" "staging_public" {
  subnet_id      = aws_subnet.staging_public.id
  route_table_id = aws_route_table.staging_public.id
}

# =========================================================================
# VPC: Shared Services (logging, monitoring, secrets)
# =========================================================================

resource "aws_vpc" "shared" {
  cidr_block           = "10.2.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "shared-services-vpc" }
}

resource "aws_subnet" "shared_a" {
  vpc_id            = aws_vpc.shared.id
  cidr_block        = "10.2.1.0/24"
  availability_zone = "us-east-1a"

  tags = { Name = "shared-a" }
}

resource "aws_subnet" "shared_b" {
  vpc_id            = aws_vpc.shared.id
  cidr_block        = "10.2.2.0/24"
  availability_zone = "us-east-1b"

  tags = { Name = "shared-b" }
}

# =========================================================================
# VPC Peering — these are high blast-radius: breaking peering severs
# cross-VPC communication for all resources
# =========================================================================

resource "aws_vpc_peering_connection" "prod_to_shared" {
  vpc_id      = aws_vpc.production.id
  peer_vpc_id = aws_vpc.shared.id
  auto_accept = true

  tags = { Name = "prod-to-shared" }
}

resource "aws_vpc_peering_connection" "staging_to_shared" {
  vpc_id      = aws_vpc.staging.id
  peer_vpc_id = aws_vpc.shared.id
  auto_accept = true

  tags = { Name = "staging-to-shared" }
}

# Shared services route table — routes back to both prod and staging
resource "aws_route_table" "shared" {
  vpc_id = aws_vpc.shared.id

  route {
    cidr_block                = "10.0.0.0/16"
    vpc_peering_connection_id = aws_vpc_peering_connection.prod_to_shared.id
  }

  route {
    cidr_block                = "10.1.0.0/16"
    vpc_peering_connection_id = aws_vpc_peering_connection.staging_to_shared.id
  }

  tags = { Name = "shared-rt" }
}

resource "aws_route_table_association" "shared_a" {
  subnet_id      = aws_subnet.shared_a.id
  route_table_id = aws_route_table.shared.id
}

resource "aws_route_table_association" "shared_b" {
  subnet_id      = aws_subnet.shared_b.id
  route_table_id = aws_route_table.shared.id
}

# =========================================================================
# Security Groups — layered, cross-referencing
# Changing the bastion SG cascades to app and db SGs
# =========================================================================

resource "aws_security_group" "bastion" {
  name        = "bastion-sg"
  description = "SSH access for operations"
  vpc_id      = aws_vpc.production.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["203.0.113.0/24"]
    description = "Office IP range"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "bastion-sg" }
}

resource "aws_security_group" "app" {
  name        = "app-sg"
  description = "App tier — accepts from bastion"
  vpc_id      = aws_vpc.production.id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    cidr_blocks     = ["0.0.0.0/0"]
    description     = "HTTP traffic"
  }

  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
    description     = "SSH from bastion"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "app-sg" }
}

resource "aws_security_group" "cache" {
  name        = "cache-sg"
  description = "Cache tier — accepts from app only"
  vpc_id      = aws_vpc.production.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
    description     = "Redis from app tier"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cache-sg" }
}

# Shared services SG — accepts traffic from both prod and staging
resource "aws_security_group" "shared_services" {
  name        = "shared-services-sg"
  description = "Shared logging/monitoring — accepts from peered VPCs"
  vpc_id      = aws_vpc.shared.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16", "10.1.0.0/16"]
    description = "HTTPS from prod and staging"
  }

  ingress {
    from_port   = 514
    to_port     = 514
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16", "10.1.0.0/16"]
    description = "Syslog from prod and staging"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "shared-services-sg" }
}

# =========================================================================
# IAM — cross-cutting roles used by multiple compute resources
# =========================================================================

resource "aws_iam_role" "app_role" {
  name = "app-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "app_s3_access" {
  name = "app-s3-access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
      ]
      Resource = [
        aws_s3_bucket.app_assets.arn,
        "${aws_s3_bucket.app_assets.arn}/*",
        aws_s3_bucket.logs.arn,
        "${aws_s3_bucket.logs.arn}/*",
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "app_s3" {
  role       = aws_iam_role.app_role.name
  policy_arn = aws_iam_policy.app_s3_access.arn
}

resource "aws_iam_policy" "app_secrets" {
  name = "app-secrets-access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
      ]
      Resource = aws_secretsmanager_secret.app_db_password.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "app_secrets" {
  role       = aws_iam_role.app_role.name
  policy_arn = aws_iam_policy.app_secrets.arn
}

resource "aws_iam_instance_profile" "app" {
  name = "app-instance-profile"
  role = aws_iam_role.app_role.name
}

# Ops role — used by bastion, has broader access
resource "aws_iam_role" "ops_role" {
  name = "ops-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "ops_admin" {
  name = "ops-admin-access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:*", "s3:*", "rds:*", "secretsmanager:*"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ops_admin" {
  role       = aws_iam_role.ops_role.name
  policy_arn = aws_iam_policy.ops_admin.arn
}

resource "aws_iam_instance_profile" "ops" {
  name = "ops-instance-profile"
  role = aws_iam_role.ops_role.name
}

# =========================================================================
# Secrets
# =========================================================================

resource "aws_secretsmanager_secret" "app_db_password" {
  name = "prod/app/db-password"
}

resource "aws_secretsmanager_secret_version" "app_db_password" {
  secret_id     = aws_secretsmanager_secret.app_db_password.id
  secret_string = "super-secret-password"
}

# =========================================================================
# Compute — instances in each tier
# =========================================================================

resource "aws_instance" "bastion" {
  ami                    = "ami-0c02fb55956c7d316"
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.prod_public_a.id
  vpc_security_group_ids = [aws_security_group.bastion.id]
  iam_instance_profile   = aws_iam_instance_profile.ops.name

  tags = { Name = "bastion" }
}

resource "aws_instance" "app_a" {
  ami                    = "ami-0c02fb55956c7d316"
  instance_type          = "t3.small"
  subnet_id              = aws_subnet.prod_private_a.id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  tags = { Name = "app-a" }
}

resource "aws_instance" "app_b" {
  ami                    = "ami-0c02fb55956c7d316"
  instance_type          = "t3.small"
  subnet_id              = aws_subnet.prod_private_b.id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  tags = { Name = "app-b" }
}

# =========================================================================
# Storage — S3 buckets referenced by IAM policies
# =========================================================================

resource "aws_s3_bucket" "app_assets" {
  bucket = "network-mesh-app-assets"
}

resource "aws_s3_bucket" "logs" {
  bucket = "network-mesh-central-logs"
}

