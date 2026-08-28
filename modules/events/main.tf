terraform {
  required_version = ">= 1.6"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}

variable "endpoint" {
  description = "The emulator's address as seen from the HOST, used by Terraform itself."
  type        = string
}

variable "endpoint_from_lambda" {
  description = <<-EOT
    The emulator's address as seen from INSIDE the Lambda container, which is not the same
    string. moto executes handlers in a container, so 127.0.0.1 there is the container's own
    loopback and reaches nothing: the first attempt returned EndpointConnectionError trying to
    call http://127.0.0.1:5599/. On Docker Desktop and colima the host is host.docker.internal.
    No default, for the same reason the other one has none.
  EOT
  type        = string
}

provider "aws" {
  region                      = "eu-west-1"
  access_key                  = "moto-demo"
  secret_key                  = "moto-demo"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true

  endpoints {
    sqs    = var.endpoint
    sns    = var.endpoint
    iam    = var.endpoint
    sts    = var.endpoint
    lambda = var.endpoint
    logs   = var.endpoint
  }
}

data "archive_file" "handler" {
  type        = "zip"
  source_file = "${path.module}/lambda/handler.py"
  output_path = "${path.module}/.build/handler.zip"
}

resource "aws_sqs_queue" "arrivals" {
  name = "quiltz-arrivals"
}

resource "aws_sns_topic" "announcements" {
  name = "quiltz-announcements"
}

# The observable terminus. SNS is fire and forget, so a test needs somewhere the notification
# lands that it can read back, and subscribing a queue is the smallest honest way to get one.
resource "aws_sqs_queue" "announced" {
  name = "quiltz-announced"
}

resource "aws_sns_topic_subscription" "announced" {
  topic_arn = aws_sns_topic.announcements.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.announced.arn
}

data "aws_iam_policy_document" "assume_by_lambda" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Named actions on named resources. The queue it may read and the topic it may publish to, and
# nothing else. parliament lints this document out of the plan like every other one here.
data "aws_iam_policy_document" "consume_and_announce" {
  statement {
    sid       = "ReadTheArrivalsQueue"
    effect    = "Allow"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.arrivals.arn]
  }
  statement {
    sid       = "AnnounceOnOneTopic"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.announcements.arn]
  }
}

resource "aws_iam_role" "consumer" {
  name               = "quiltz-consumer"
  assume_role_policy = data.aws_iam_policy_document.assume_by_lambda.json
}

resource "aws_iam_policy" "consume_and_announce" {
  name   = "quiltz-consume-and-announce"
  policy = data.aws_iam_policy_document.consume_and_announce.json
}

resource "aws_iam_role_policy_attachment" "consumer" {
  role       = aws_iam_role.consumer.name
  policy_arn = aws_iam_policy.consume_and_announce.arn
}

resource "aws_lambda_function" "consumer" {
  function_name    = "quiltz-consumer"
  role             = aws_iam_role.consumer.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.handler.output_path
  source_code_hash = data.archive_file.handler.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      QUILTZ_ENDPOINT  = var.endpoint_from_lambda
      QUILTZ_TOPIC_ARN = aws_sns_topic.announcements.arn
    }
  }
}

resource "aws_lambda_event_source_mapping" "arrivals" {
  event_source_arn = aws_sqs_queue.arrivals.arn
  function_name    = aws_lambda_function.consumer.arn
  batch_size       = 1
  enabled          = true
}

output "arrivals_queue_url" { value = aws_sqs_queue.arrivals.url }
output "announced_queue_url" { value = aws_sqs_queue.announced.url }
output "topic_arn" { value = aws_sns_topic.announcements.arn }
output "function_name" { value = aws_lambda_function.consumer.function_name }
