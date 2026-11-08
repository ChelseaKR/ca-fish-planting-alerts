locals {
  name = "trout-truck-web-push"

  # Both spellings, as in the portfolio's other stacks: the payer account's
  # cost-allocation tags are the lowercase pair.
  tags = {
    Project     = "trout-truck"
    Environment = "production"
    ManagedBy   = "terraform"
    project     = "trout-truck"
    environment = "production"
  }

  origins = concat([var.site_origin], var.extra_origins)
}

# --- The table ----------------------------------------------------------------
# One table: a row per browser (pk "SUB#<sha256 of the endpoint>": the water,
# the endpoint, its two keys, created_at, last_sent_at, expires_at) and one
# "COUNTERS" row of totals. by_water is the send fan-out; the counters row
# has no water_id and so is not in it. DynamoDB's TTL drops a subscription
# nothing has been sent to for about 13 months (handler.mjs refreshes
# expires_at on every successful send).
resource "aws_dynamodb_table" "subscriptions" {
  name         = local.name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "water_id"
    type = "S"
  }

  global_secondary_index {
    name            = "by_water"
    projection_type = "ALL"

    key_schema {
      attribute_name = "water_id"
      key_type       = "HASH"
    }
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # Encrypted at rest with the AWS managed key aws/dynamodb (visible in
  # CloudTrail, no monthly key fee).
  server_side_encryption {
    enabled = true
  }

  # No point-in-time recovery: a subscription is recreated by its owner in two
  # taps, and the totals are the measurement of a test, not a ledger.
  point_in_time_recovery {
    enabled = false
  }

  deletion_protection_enabled = var.protect_table
}

# --- The function ---------------------------------------------------------------
data "archive_file" "function" {
  type        = "zip"
  source_dir  = "${path.module}/${var.lambda_dir}"
  output_path = "${path.module}/${local.name}.zip"
  excludes    = ["handler.test.mjs", "validate.test.mjs", ".gitignore"]
}

resource "aws_cloudwatch_log_group" "function" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "function" {
  name               = local.name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "function" {
  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.subscriptions.arn,
      "${aws_dynamodb_table.subscriptions.arn}/index/*",
    ]
  }
  # The four parameters under the prefix, decrypted. The SecureStrings use
  # the account's AWS managed key aws/ssm, whose key policy lets a principal
  # in this account decrypt through SSM, so no KMS statement is needed.
  statement {
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${var.region}:${var.aws_account_id}:parameter${var.ssm_prefix}/*"]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.function.arn}:*"]
  }
}

resource "aws_iam_role_policy" "function" {
  name   = local.name
  role   = aws_iam_role.function.id
  policy = data.aws_iam_policy_document.function.json
}

resource "aws_lambda_function" "service" {
  function_name = local.name
  role          = aws_iam_role.function.arn
  runtime       = "nodejs22.x"
  architectures = ["arm64"]
  handler       = "index.handler"
  memory_size   = 256
  # One /send call is at most 100 waters, each fanned out to its subscribers
  # ten at a time with a five-second cap; a subscribe is milliseconds. The
  # pipeline's client waits longer than this (cfpa.push.send_events).
  timeout = 120

  filename         = data.archive_file.function.output_path
  source_code_hash = data.archive_file.function.output_base64sha256

  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      TABLE_NAME   = aws_dynamodb_table.subscriptions.name
      SSM_PREFIX   = var.ssm_prefix
      SITE_ORIGINS = join(",", local.origins)
    }
  }

  depends_on = [aws_cloudwatch_log_group.function, aws_iam_role_policy.function]
}

# A public function URL: no API Gateway to pay for. CORS lets only the site's
# own origin call it from a browser; the token routes are called by the
# publish workflow, not a browser, and check a bearer token themselves.
resource "aws_lambda_function_url" "service" {
  function_name      = aws_lambda_function.service.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = local.origins
    allow_methods = ["POST"]
    allow_headers = ["content-type"]
    max_age       = 86400
  }
}

# Public function URLs need both permissions (AWS changed this in late 2025).
resource "aws_lambda_permission" "url_invoke" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.service.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "url_invoke_function" {
  statement_id             = "AllowPublicInvokeViaUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.service.function_name
  principal                = "*"
  invoked_via_function_url = true
}

# --- A spending alarm ------------------------------------------------------------
resource "aws_budgets_budget" "monthly" {
  count        = var.budget_email == "" ? 0 : 1
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = "5"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}
