terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.52"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

# Local state on purpose for a 60-day test: no state bucket, no lock table,
# nothing else to pay for. State holds no secret (the VAPID keys and the
# sender token live in SSM and are never read by Terraform), but it names the
# account and the table, so it stays out of git (../../.gitignore).
provider "aws" {
  region = var.region
  # The portfolio rule: each app's resources live in that app's own member
  # account. This refuses to run against any other account.
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = local.tags
  }
}
