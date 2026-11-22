provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  default_tags {
    tags = { project = "alphalake" }
  }
}

# The Snowflake side (database, roles, warehouses, users, storage integration) is created by
# infra/snowflake/setup.sql, run in Snowsight. This Terraform only manages AWS.
