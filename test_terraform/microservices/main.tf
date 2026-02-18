# main.tf — Event-Driven Microservices Architecture
# Tests blast radius: shared IAM roles cascade to many Lambdas/queues,
# deep dependency chains through SQS → Lambda → DynamoDB → S3.

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
    dynamodb       = "http://127.0.0.1:4566"
    ec2            = "http://127.0.0.1:4566"
    iam            = "http://127.0.0.1:4566"
    lambda         = "http://127.0.0.1:4566"
    s3             = "http://127.0.0.1:4566"
    sns            = "http://127.0.0.1:4566"
    sqs            = "http://127.0.0.1:4566"
    sts            = "http://127.0.0.1:4566"
    secretsmanager = "http://127.0.0.1:4566"
    cloudwatch     = "http://127.0.0.1:4566"
  }
}

# ---------------------------------------------------------------------------
# Shared IAM — changing these cascades to ALL services below
# ---------------------------------------------------------------------------

resource "aws_iam_role" "service_execution" {
  name = "microservices-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      # Effect = "Deny"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "service_base" {
  name = "microservices-base-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "service_base_attach" {
  role       = aws_iam_role.service_execution.name
  policy_arn = aws_iam_policy.service_base.arn
}

resource "aws_iam_policy" "sns_publish" {
  name = "microservices-sns-publish"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "sns_publish_attach" {
  role       = aws_iam_role.service_execution.name
  policy_arn = aws_iam_policy.sns_publish.arn
}

resource "aws_iam_policy" "secrets_read" {
  name = "microservices-secrets-read"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
      ]
      Resource = aws_secretsmanager_secret.db_credentials.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "secrets_read_attach" {
  role       = aws_iam_role.service_execution.name
  policy_arn = aws_iam_policy.secrets_read.arn
}

# ---------------------------------------------------------------------------
# Secrets — database credentials consumed by services
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "db_credentials" {
  name = "microservices/db-credentials"
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    host     = "db.internal"
    port     = 5432
    username = "app"
    password = "changeme"
  })
}

# ---------------------------------------------------------------------------
# Event Bus — SNS fan-out topic
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "events" {
  name = "microservices-events"
}

# ---------------------------------------------------------------------------
# Order Service — ingests orders, writes to DynamoDB, publishes to SNS
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "orders_dlq" {
  name = "orders-dlq"
}

resource "aws_sqs_queue" "orders" {
  name = "orders-queue"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.orders_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_lambda_function" "order_processor" {
  function_name = "order-processor"
  role          = aws_iam_role.service_execution.arn
  handler       = "order.handler"
  runtime       = "python3.11"
  filename      = "order.zip"

  environment {
    variables = {
      ORDERS_TABLE = aws_dynamodb_table.orders.name
      EVENTS_TOPIC = aws_sns_topic.events.arn
      DB_SECRET    = aws_secretsmanager_secret.db_credentials.name
    }
  }
}

resource "aws_lambda_event_source_mapping" "orders_trigger" {
  event_source_arn = aws_sqs_queue.orders.arn
  function_name    = aws_lambda_function.order_processor.arn
  batch_size       = 10
}

resource "aws_dynamodb_table" "orders" {
  name         = "orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"

  attribute {
    name = "order_id"
    type = "S"
  }
}

# ---------------------------------------------------------------------------
# Payment Service — processes payments, notified via SNS → SQS
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "payments_dlq" {
  name = "payments-dlq"
}

resource "aws_sqs_queue" "payments" {
  name = "payments-queue"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.payments_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sns_topic_subscription" "payments_sub" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.payments.arn
}

resource "aws_lambda_function" "payment_processor" {
  function_name = "payment-processor"
  role          = aws_iam_role.service_execution.arn
  handler       = "payment.handler"
  runtime       = "python3.11"
  filename      = "payment.zip"

  environment {
    variables = {
      PAYMENTS_TABLE = aws_dynamodb_table.payments.name
      DB_SECRET      = aws_secretsmanager_secret.db_credentials.name
    }
  }
}

resource "aws_lambda_event_source_mapping" "payments_trigger" {
  event_source_arn = aws_sqs_queue.payments.arn
  function_name    = aws_lambda_function.payment_processor.arn
  batch_size       = 5
}

resource "aws_dynamodb_table" "payments" {
  name         = "payments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "payment_id"

  attribute {
    name = "payment_id"
    type = "S"
  }
}

# ---------------------------------------------------------------------------
# Notification Service — sends emails/alerts, notified via SNS → SQS
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "notifications" {
  name = "notifications-queue"
}

resource "aws_sns_topic_subscription" "notifications_sub" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.notifications.arn
}

resource "aws_lambda_function" "notifier" {
  function_name = "notifier"
  role          = aws_iam_role.service_execution.arn
  handler       = "notify.handler"
  runtime       = "python3.11"
  filename      = "notify.zip"

  environment {
    variables = {
      NOTIFICATION_LOG_TABLE = aws_dynamodb_table.notification_log.name
    }
  }
}

resource "aws_lambda_event_source_mapping" "notifications_trigger" {
  event_source_arn = aws_sqs_queue.notifications.arn
  function_name    = aws_lambda_function.notifier.arn
  batch_size       = 10
}

resource "aws_dynamodb_table" "notification_log" {
  name         = "notification-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "notification_id"

  attribute {
    name = "notification_id"
    type = "S"
  }
}

# ---------------------------------------------------------------------------
# Archive Service — stores processed events in S3
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "event_archive" {
  bucket = "microservices-event-archive"
}

resource "aws_lambda_function" "archiver" {
  function_name = "event-archiver"
  role          = aws_iam_role.service_execution.arn
  handler       = "archive.handler"
  runtime       = "python3.11"
  filename      = "archive.zip"

  environment {
    variables = {
      ARCHIVE_BUCKET = aws_s3_bucket.event_archive.id
    }
  }
}

resource "aws_sns_topic_subscription" "archive_sub" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.archive.arn
}

resource "aws_sqs_queue" "archive" {
  name = "archive-queue"
}

resource "aws_lambda_event_source_mapping" "archive_trigger" {
  event_source_arn = aws_sqs_queue.archive.arn
  function_name    = aws_lambda_function.archiver.arn
  batch_size       = 10
}

# ---------------------------------------------------------------------------
# Monitoring — CloudWatch alarms on DLQs
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "orders_dlq_alarm" {
  alarm_name          = "orders-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Orders DLQ has messages — processing failures"

  dimensions = {
    QueueName = aws_sqs_queue.orders_dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "payments_dlq_alarm" {
  alarm_name          = "payments-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Payments DLQ has messages — processing failures"

  dimensions = {
    QueueName = aws_sqs_queue.payments_dlq.name
  }
}
