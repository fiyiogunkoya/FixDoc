# # main.tf — Realistic multi-tier AWS application
# # Pointed at LocalStack for local testing with fixdoc.
# # Edit freely — add/remove resources, break things on purpose.

# terraform {
#   required_providers {
#     aws = {
#       source  = "hashicorp/aws"
#       version = "~> 5.0"
#     }
#   }
# }

# provider "aws" {
#   region                      = "us-east-1"
#   access_key                  = "test"
#   secret_key                  = "test"
#   skip_credentials_validation = true
#   skip_metadata_api_check     = true
#   skip_requesting_account_id  = true
#   s3_use_path_style           = true

#   endpoints {
#     ec2            = "http://localhost:4566"
#     iam            = "http://localhost:4566"
#     lambda         = "http://localhost:4566"
#     s3             = "http://localhost:4566"
#     sts            = "http://localhost:4566"
#   }
# }

# variable "bucket_name" {
#   type    = string
#   default = "fixdoc-app-data"
# }

# # ---------------------------------------------------------------------------
# # Networking
# # ---------------------------------------------------------------------------

# resource "aws_vpc" "main" {
#   cidr_block           = "10.0.0.0/16"
#   enable_dns_hostnames = true
#   enable_dns_support   = true

#   tags = {
#     Name = "fixdoc-vpc"
#   }
# }

# resource "aws_subnet" "public" {
#   vpc_id                  = aws_vpc.main.id
#   cidr_block              = "10.0.1.0/24"
#   availability_zone       = "us-east-1a"
#   map_public_ip_on_launch = true

#   tags = {
#     Name = "fixdoc-public"
#   }
# }

# resource "aws_subnet" "private" {
#   vpc_id            = aws_vpc.main.id
#   cidr_block        = "10.0.2.0/24"
#   availability_zone = "us-east-1b"

#   tags = {
#     Name = "fixdoc-private"
#   }
# }

# resource "aws_security_group" "web" {
#   name        = "fixdoc-web-sg"
#   description = "Allow HTTP/HTTPS inbound"
#   vpc_id      = aws_vpc.main.id

#   ingress {
#     from_port   = 80
#     to_port     = 80
#     protocol    = "tcp"
#     cidr_blocks = ["0.0.0.0/0"]
#   }

#   ingress {
#     from_port   = 443
#     to_port     = 443
#     protocol    = "tcp"
#     cidr_blocks = ["0.0.0.0/0"]
#   }

#   egress {
#     from_port   = 0
#     to_port     = 0
#     protocol    = "-1"
#     cidr_blocks = ["0.0.0.0/0"]
#   }

#   tags = {
#     Name = "fixdoc-web-sg"
#   }
# }

# # ---------------------------------------------------------------------------
# # Compute
# # ---------------------------------------------------------------------------

# resource "aws_instance" "web" {
#   ami                    = "ami-0c02fb55956c7d316"
#   instance_type          = "t3.micro"
#   subnet_id              = aws_subnet.public.id
#   vpc_security_group_ids = [aws_security_group.web.id]

#   tags = {
#     Name = "fixdoc-web"
#   }
# }

# # ---------------------------------------------------------------------------
# # Serverless
# # ---------------------------------------------------------------------------

# resource "aws_iam_role" "lambda_exec" {
#   name = "fixdoc-lambda-exec"

#   assume_role_policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [{
#       Action = "sts:AssumeRole"
#       Effect = "Allow"
#       Principal = {
#         Service = "lambda.amazonaws.com"
#       }
#     }]
#   })
# }

# resource "aws_iam_role_policy_attachment" "lambda_basic" {
#   role       = aws_iam_role.lambda_exec.name
#   policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
# }

# resource "aws_lambda_function" "api" {
#   function_name = "fixdoc-api"
#   role          = aws_iam_role.lambda_exec.arn
#   handler       = "index.handler"
#   runtime       = "python3.11"
#   filename      = "lambda.zip"

#   environment {
#     variables = {
#       BUCKET_NAME = aws_s3_bucket.data.id
#     }
#   }
# }

# # ---------------------------------------------------------------------------
# # Storage
# # ---------------------------------------------------------------------------

# resource "aws_s3_bucket" "data" {
#   bucket = var.bucket_name
# }

# resource "aws_s3_bucket" "today" {

# }

# resource "aws_rds" "rds"{

# }

# resource "aws_redis_cache" "test"{

# }

# resource "aws_dynamodb_table" "test_table_a" {
# }

# resource "aws_lambda_function" "myfunction" {
# }

# resource "aws_appsync_graphql_api" "test_api" {
#   authentication_type = "API_KEY"
# }

# resource "aws_keyspaces_table" "mykeyspacestable" {
# } 
