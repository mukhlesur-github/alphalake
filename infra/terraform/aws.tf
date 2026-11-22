data "aws_caller_identity" "current" {}

locals {
  bucket_name        = "alphalake-landing-${data.aws_caller_identity.current.account_id}"
  snowflake_role     = "alphalake-snowflake-s3-read"
  snowflake_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.snowflake_role}"
  # We choose the external ID ourselves. That breaks the usual chicken-and-egg loop:
  # the integration can be created before the IAM role exists, and the role's trust
  # policy references the integration's IAM user + this ID.
  external_id = "alphalake_${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "landing" {
  bucket        = local.bucket_name
  force_destroy = true # learning project: `terraform destroy` must be able to empty it
}

resource "aws_s3_bucket_public_access_block" "landing" {
  bucket                  = aws_s3_bucket.landing.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "landing" {
  bucket = aws_s3_bucket.landing.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- Snowflake -> S3 trust (storage integration handshake) -------------------------

data "aws_iam_policy_document" "snowflake_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [snowflake_storage_integration_aws.landing.describe_output[0].iam_user_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [local.external_id]
    }
  }
}

resource "aws_iam_role" "snowflake" {
  name               = local.snowflake_role
  assume_role_policy = data.aws_iam_policy_document.snowflake_trust.json
}

data "aws_iam_policy_document" "snowflake_s3_read" {
  statement {
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.landing.arn}/landing/*"]
  }
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.landing.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["landing/*"]
    }
  }
}

resource "aws_iam_role_policy" "snowflake_s3_read" {
  role   = aws_iam_role.snowflake.id
  policy = data.aws_iam_policy_document.snowflake_s3_read.json
}

# --- S3 -> Snowpipe auto-ingest notification (second apply) -------------------------

resource "aws_s3_bucket_notification" "snowpipe" {
  count  = var.snowpipe_sqs_arn == "" ? 0 : 1
  bucket = aws_s3_bucket.landing.id
  queue {
    queue_arn     = var.snowpipe_sqs_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "landing/"
  }
}

# --- Cost guardrail -----------------------------------------------------------------

resource "aws_budgets_budget" "monthly" {
  name         = "alphalake-monthly"
  budget_type  = "COST"
  limit_amount = "1"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 1
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}
