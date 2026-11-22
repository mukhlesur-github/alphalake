provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  default_tags {
    tags = { project = "alphalake" }
  }
}

# Terraform authenticates to Snowflake as a bootstrap service user (key-pair, ACCOUNTADMIN).
# Create it once with infra/bootstrap/bootstrap.sql.
provider "snowflake" {
  organization_name = var.snowflake_organization_name
  account_name      = var.snowflake_account_name
  user              = "SVC_ALPHALAKE_TERRAFORM"
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file("${path.root}/../../keys/svc_alphalake_terraform.p8")
  role              = "ACCOUNTADMIN"

  preview_features_enabled = ["snowflake_storage_integration_aws_resource"]
}
