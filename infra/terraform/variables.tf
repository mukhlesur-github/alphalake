variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "aws_profile" {
  type    = string
  default = "alphalake"
}

variable "snowflake_organization_name" {
  type        = string
  description = "First half of the account identifier <org>-<account> (Snowsight > Admin > Accounts)."
}

variable "snowflake_account_name" {
  type        = string
  description = "Second half of the account identifier <org>-<account>."
}

variable "budget_email" {
  type        = string
  description = "Email for the AWS budget alert."
}

variable "credit_quota" {
  type        = number
  default     = 40
  description = "Monthly Snowflake credit cap for AlphaLake warehouses (trial has ~$400 of credits)."
}

# Phase 2 wiring: Snowpipe auto-ingest uses one Snowflake-owned SQS queue per account.
# It only exists after the first pipe is created, so it's filled in on a second apply
# (`make wire-snowpipe`). Empty = no bucket notification yet.
variable "snowpipe_sqs_arn" {
  type    = string
  default = ""
}
