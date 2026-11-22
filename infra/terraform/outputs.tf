output "bucket" {
  value = aws_s3_bucket.landing.bucket
}

output "snowflake_iam_role_arn" {
  value = aws_iam_role.snowflake.arn
}
