variable "aws_account_id" {
  description = "The 12-digit ID of the AWS member account that belongs to Trout Truck alone (trouttruck). The provider refuses any other account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "region" {
  description = "AWS region. us-east-1 is where the portfolio's other apps run."
  type        = string
  default     = "us-east-1"
}

variable "site_origin" {
  description = "The site's https origin with no trailing slash, e.g. https://trouttruck.com. Only this origin (and extra_origins) may call the function from a browser, and a message may link only to a page under it."
  type        = string

  validation {
    condition     = can(regex("^https://[a-z0-9.-]+$", var.site_origin))
    error_message = "site_origin must look like https://example.com (https, no path, no trailing slash)."
  }
}

variable "extra_origins" {
  description = "More https origins allowed to call the function from a browser and to be linked from a message, e.g. a staging host."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for o in var.extra_origins : can(regex("^https://[a-z0-9.-]+$", o))])
    error_message = "Each extra origin must look like https://example.com (https, no path, no trailing slash)."
  }
}

variable "lambda_dir" {
  description = "Directory holding index.mjs, handler.mjs, dynamo.mjs, validate.mjs and node_modules/ (run `npm ci --omit=dev` in it first; README)."
  type        = string
  default     = "lambda"
}

variable "ssm_prefix" {
  description = "SSM Parameter Store path the function reads its four parameters under: vapid-public-key, vapid-private-key, vapid-subject, sender-token. The owner writes them (README); Terraform never reads their values."
  type        = string
  default     = "/trout-truck/web-push"

  validation {
    condition     = can(regex("^/[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$", var.ssm_prefix))
    error_message = "ssm_prefix must start with / and have no trailing slash."
  }
}

variable "reserved_concurrency" {
  description = "Hard ceiling on parallel invocations. -1 means unreserved. A member account with the default concurrency quota of 10 cannot reserve any, so the default is -1; set 2 once the quota is raised."
  type        = number
  default     = -1
}

variable "protect_table" {
  description = "Deletion protection on the table. Off for the 60-day test: a subscription is something a visitor recreates in two taps, not a record. Set true if the test becomes a product."
  type        = bool
  default     = false
}

variable "budget_email" {
  description = "Where to send a warning when the account's monthly spend passes 80% of $5. Empty creates no budget."
  type        = string
  default     = ""
}
