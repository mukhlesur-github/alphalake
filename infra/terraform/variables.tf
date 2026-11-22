variable "aws_region" {
  type    = string
  default = "ap-southeast-1" # must match the Snowflake account region (AWS_AP_SOUTHEAST_1)
}

variable "aws_profile" {
  type    = string
  default = "alphalake"
}

variable "budget_email" {
  type        = string
  description = "Email for the AWS budget alert."
}

# From `DESC INTEGRATION ALPHALAKE_S3_INT` -> STORAGE_AWS_IAM_USER_ARN (created by infra/snowflake/setup.sql).
variable "snowflake_iam_user_arn" {
  type        = string
  description = "Snowflake's IAM user that assumes the S3 read role."
}

# Phase 2 wiring: Snowpipe auto-ingest uses one Snowflake-owned SQS queue per account.
# It only exists after the first pipe is created (V001), so it's filled in on a second apply.
# Empty = no bucket notification yet.
variable "snowpipe_sqs_arn" {
  type    = string
  default = ""
}
