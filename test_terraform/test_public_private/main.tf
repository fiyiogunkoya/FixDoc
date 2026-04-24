terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
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
  }
}

############################
# Variables (keep in main.tf)
############################

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

# Toggle 1: make the "private" subnet effectively public.
# This should create clear routing + subnet changes for analyze.
variable "make_private_subnet_public" {
  type    = bool
  default = true
}

# Toggle 2: open inbound to the "app" security group.
# This should show boundary/security changes clearly.
variable "open_to_internet" {
  type    = bool
  default = true
}

variable "project" {
  type    = string
  default = "fixdoc-analyze-lab"
}

locals {
  tags = {
    Project = var.project
    Owner   = "fixdoc"
  }
}

############################
# Networking
############################

resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.tags, { Name = "${var.project}-vpc" })
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = merge(local.tags, { Name = "${var.project}-igw" })
}

# Public subnet
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = merge(local.tags, { Name = "${var.project}-subnet-public" })
}

# "Private" subnet (but can be flipped public via toggle)
resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.aws_region}a"

  # When toggled, instances launched in this subnet get public IPs.
  map_public_ip_on_launch = var.make_private_subnet_public

  tags = merge(local.tags, { Name = "${var.project}-subnet-private" })
}

# Public route table: 0.0.0.0/0 -> IGW
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = merge(local.tags, { Name = "${var.project}-rt-public" })
}

# "Private" route table (no default internet route)
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  tags   = merge(local.tags, { Name = "${var.project}-rt-private" })
}

# Associate public subnet to public route table
resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Associate "private" subnet either to private RT (default)
# or to the public RT (toggle) to make it public.
resource "aws_route_table_association" "private_assoc" {
  subnet_id = aws_subnet.private.id

  route_table_id = var.make_private_subnet_public? aws_route_table.public.id : aws_route_table.private.id
}

############################
# Security
############################

# App SG: optionally open to internet
resource "aws_security_group" "app" {
  name        = "${var.project}-sg-app"
  description = "App security group for FixDoc analyze testing"
  vpc_id      = aws_vpc.main.id

  # Egress open (common default)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${var.project}-sg-app" })
}

# Ingress rules are separate resources so toggles create clean plan diffs
resource "aws_security_group_rule" "ssh_internet" {
  count             = var.open_to_internet ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.app.id
  protocol          = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "SSH from internet (for testing only)"
}

resource "aws_security_group_rule" "http_internet" {
  count             = var.open_to_internet ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.app.id
  protocol          = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTP from internet (for testing only)"
}

############################
# Compute (2 instances)
############################

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64*"]
  }
}

resource "aws_instance" "public" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  subnet_id                    = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.app.id]
  associate_public_ip_address = true

  tags = merge(local.tags, { Name = "${var.project}-ec2-public" })
}

resource "aws_instance" "private" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.private.id
  vpc_security_group_ids = [aws_security_group.app.id]

  # If the subnet is flipped to public, this instance becomes internet-addressable.
  associate_public_ip_address = var.make_private_subnet_public

  tags = merge(local.tags, { Name = "${var.project}-ec2-private" })
}

############################
# Helpful outputs (optional)
############################

output "toggles" {
  value = {
    make_private_subnet_public = var.make_private_subnet_public
    open_to_internet           = var.open_to_internet
  }
}