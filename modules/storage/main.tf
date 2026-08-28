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
  description = "The emulator's address. There is no default: a module that silently talks to AWS when a variable is unset is the accident this repository exists to avoid."
  type        = string
}

variable "bucket_name" {
  type = string
}

provider "aws" {
  region                      = "eu-west-1"
  access_key                  = "moto-demo"
  secret_key                  = "moto-demo"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    s3  = var.endpoint
    sqs = var.endpoint
    sns = var.endpoint
    iam = var.endpoint
    sts = var.endpoint
  }
}

resource "aws_s3_bucket" "evidence" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration {
    status = "Enabled"
  }
}

output "bucket" {
  value = aws_s3_bucket.evidence.id
}
