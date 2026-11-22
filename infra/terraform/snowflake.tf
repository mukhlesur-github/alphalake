locals {
  db       = "ALPHALAKE"
  schemas  = ["BRONZE", "SILVER", "GOLD", "SEMANTIC", "DOCS", "AUDIT"]
  personas = ["ALPHALAKE_PM", "ALPHALAKE_ANALYST"]
  # Personas read the modelled layers only, never BRONZE/SILVER. DOCS tables are NOT readable:
  # documents are reached only through Cortex Search services, granted per access tier in V004.
  persona_read_schemas = ["GOLD", "SEMANTIC"]

  # Public key body without PEM header/footer, as Snowflake expects.
  pubkey = { for u in ["pipeline", "app"] : u => join("", [
    for l in split("\n", trimspace(file("${path.root}/../../keys/svc_alphalake_${u}.pub"))) : l
    if !startswith(l, "-----")
  ]) }
}

# --- Containers ----------------------------------------------------------------------

resource "snowflake_database" "alphalake" {
  name                        = local.db
  data_retention_time_in_days = 1
}

resource "snowflake_schema" "s" {
  for_each = toset(local.schemas)
  database = snowflake_database.alphalake.name
  name     = each.key
}

# --- Compute + cost guardrail --------------------------------------------------------

resource "snowflake_resource_monitor" "alphalake" {
  name                      = "ALPHALAKE_RM"
  credit_quota              = var.credit_quota
  frequency                 = "MONTHLY"
  start_timestamp           = "IMMEDIATELY"
  notify_triggers           = [50, 80]
  suspend_trigger           = 95
  suspend_immediate_trigger = 100
}

resource "snowflake_warehouse" "wh" {
  for_each            = toset(["ALPHALAKE_WH_PIPELINE", "ALPHALAKE_WH_APP"])
  name                = each.key
  warehouse_size      = "XSMALL"
  auto_suspend        = 60
  auto_resume         = true
  initially_suspended = true
  resource_monitor    = snowflake_resource_monitor.alphalake.name
}

# --- Roles ---------------------------------------------------------------------------

resource "snowflake_account_role" "engineer" {
  name    = "ALPHALAKE_ENGINEER"
  comment = "Builds and runs pipelines, migrations and dbt. Owns all objects inside the schemas."
}

resource "snowflake_account_role" "persona" {
  for_each = toset(local.personas)
  name     = each.key
}

# Roll everything up to SYSADMIN so a human admin can see it all.
resource "snowflake_grant_account_role" "to_sysadmin" {
  for_each         = toset(concat(["ALPHALAKE_ENGINEER"], local.personas))
  role_name        = each.key
  parent_role_name = "SYSADMIN"
  depends_on       = [snowflake_account_role.engineer, snowflake_account_role.persona]
}

# Engineer: full control inside the database.
resource "snowflake_grant_privileges_to_account_role" "engineer_db" {
  account_role_name = snowflake_account_role.engineer.name
  privileges        = ["USAGE", "CREATE SCHEMA", "MONITOR"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.alphalake.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_schemas" {
  for_each          = snowflake_schema.s
  account_role_name = snowflake_account_role.engineer.name
  all_privileges    = true
  on_schema {
    schema_name = each.value.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_wh" {
  for_each          = snowflake_warehouse.wh
  account_role_name = snowflake_account_role.engineer.name
  privileges        = ["USAGE", "OPERATE", "MONITOR"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = each.value.name
  }
}

# Tasks run as their owner; the owner needs EXECUTE TASK at account level.
resource "snowflake_grant_privileges_to_account_role" "engineer_execute_task" {
  account_role_name = snowflake_account_role.engineer.name
  privileges        = ["EXECUTE TASK"]
  on_account        = true
}

resource "snowflake_grant_privileges_to_account_role" "engineer_integration" {
  account_role_name = snowflake_account_role.engineer.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "INTEGRATION"
    object_name = snowflake_storage_integration_aws.landing.name
  }
}

# Personas: read GOLD / SEMANTIC, use the app warehouse.
resource "snowflake_grant_privileges_to_account_role" "persona_db" {
  for_each          = snowflake_account_role.persona
  account_role_name = each.value.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.alphalake.name
  }
}

locals {
  persona_schema_pairs = { for p in setproduct(local.personas, concat(local.persona_read_schemas, ["DOCS", "AUDIT"])) : "${p[0]}.${p[1]}" => { role = p[0], schema = p[1] } }
  persona_read_pairs   = { for p in setproduct(local.personas, local.persona_read_schemas, ["TABLES", "VIEWS"]) : "${p[0]}.${p[1]}.${p[2]}" => { role = p[0], schema = p[1], kind = p[2] } }
}

resource "snowflake_grant_privileges_to_account_role" "persona_schema_usage" {
  for_each          = local.persona_schema_pairs
  account_role_name = snowflake_account_role.persona[each.value.role].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.s[each.value.schema].fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "persona_select_future" {
  for_each          = local.persona_read_pairs
  account_role_name = snowflake_account_role.persona[each.value.role].name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = each.value.kind
      in_schema          = snowflake_schema.s[each.value.schema].fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "persona_wh" {
  for_each          = snowflake_account_role.persona
  account_role_name = each.value.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh["ALPHALAKE_WH_APP"].name
  }
}

# --- Service users (key-pair only, no passwords) -------------------------------------

resource "snowflake_service_user" "pipeline" {
  name                           = "SVC_ALPHALAKE_PIPELINE"
  default_role                   = snowflake_account_role.engineer.name
  default_warehouse              = "ALPHALAKE_WH_PIPELINE"
  default_secondary_roles_option = "NONE"
  rsa_public_key                 = local.pubkey["pipeline"]
}

resource "snowflake_service_user" "app" {
  name                           = "SVC_ALPHALAKE_APP"
  default_role                   = "ALPHALAKE_ANALYST" # least privileged by default
  default_warehouse              = "ALPHALAKE_WH_APP"
  default_secondary_roles_option = "NONE" # role inheritance relies on exactly one active role
  rsa_public_key                 = local.pubkey["app"]
}

resource "snowflake_grant_account_role" "pipeline_engineer" {
  role_name = snowflake_account_role.engineer.name
  user_name = snowflake_service_user.pipeline.name
}

resource "snowflake_grant_account_role" "app_personas" {
  for_each  = snowflake_account_role.persona
  role_name = each.value.name
  user_name = snowflake_service_user.app.name
}

# --- Storage integration (Snowflake side of the S3 trust) ----------------------------

resource "snowflake_storage_integration_aws" "landing" {
  name                      = "ALPHALAKE_S3_INT"
  enabled                   = true
  storage_provider          = "S3"
  storage_aws_role_arn      = local.snowflake_role_arn
  storage_aws_external_id   = local.external_id
  storage_allowed_locations = ["s3://${local.bucket_name}/landing/"]
}
