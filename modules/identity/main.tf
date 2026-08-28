terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "endpoint" {
  description = "The emulator's address. No default on purpose: a module that talks to AWS when a variable is unset is the accident this repository exists to avoid."
  type        = string
}

variable "bucket_arn" {
  description = "The bucket this role may read, named rather than wildcarded, which is the whole point of the policy below."
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
    iam = var.endpoint
    sts = var.endpoint
  }
}

# The reader. It may get objects from one named bucket and list that bucket, and nothing else.
# Every widening of this is a finding parliament reports, which is the point of linting the
# policy the module produces rather than a policy somebody wrote for a slide.
data "aws_iam_policy_document" "read_one_bucket" {
  statement {
    sid       = "ReadObjectsInOneBucket"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/*"]
  }

  statement {
    sid       = "ListThatBucketOnly"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]
  }
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

resource "aws_iam_role" "reader" {
  name               = "quiltz-reader"
  assume_role_policy = data.aws_iam_policy_document.assume_by_lambda.json
}

resource "aws_iam_policy" "read_one_bucket" {
  name   = "quiltz-read-one-bucket"
  policy = data.aws_iam_policy_document.read_one_bucket.json
}

resource "aws_iam_role_policy_attachment" "reader" {
  role       = aws_iam_role.reader.name
  policy_arn = aws_iam_policy.read_one_bucket.arn
}

output "role_name" {
  value = aws_iam_role.reader.name
}
