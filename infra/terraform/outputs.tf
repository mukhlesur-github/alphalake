output "bucket" {
  value = aws_s3_bucket.landing.bucket
}

output "snowflake_iam_role_arn" {
  value = aws_iam_role.snowflake.arn
}

output "storage_integration_iam_user" {
  value = snowflake_storage_integration_aws.landing.describe_output[0].iam_user_arn
}
