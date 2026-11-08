output "function_url" {
  description = "Set the repository variable PUSH_API_URL to this, without the trailing slash (cfpa.push strips one anyway)."
  value       = aws_lambda_function_url.service.function_url
}

output "table_name" {
  description = "The subscriptions and counters table."
  value       = aws_dynamodb_table.subscriptions.name
}

output "log_group" {
  description = "The function's log group (14-day retention; counts and status codes, never an endpoint)."
  value       = aws_cloudwatch_log_group.function.name
}
