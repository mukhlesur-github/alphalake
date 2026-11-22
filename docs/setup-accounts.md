# Account Setup (MVP, $0)

Everything below uses the **exact names the code expects**. Never paste secrets or private keys into chat or git:
they live in `.env` and `keys/` (both git-ignored).

## Names at a glance

| Thing | Value | Where it's used |
|---|---|---|
| AWS region | `ap-southeast-1` (Singapore) | `.env` `AWS_REGION`, `terraform.tfvars` |
| AWS account id | 12 digits | `.env` `AWS_ACCOUNT_ID` (rendered into the storage integration) |
| AWS CLI profile | `alphalake` | `.env` `AWS_PROFILE`, Terraform provider, `make upload` / `make stream` |
| S3 bucket | `alphalake-landing-<your-aws-account-id>` (Terraform creates it) | auto-written to `.env` |
| Snowflake edition / cloud / region | **Enterprise** if offered (Standard works, see `GOVERNANCE_MODE`), **AWS**, **Asia Pacific (Singapore)** | trial signup |
| Snowflake account identifier | `<ORGNAME>-<ACCOUNTNAME>` (Snowsight → Admin → Accounts) | `.env` `SNOWFLAKE_ACCOUNT` |
| Snowflake database | `ALPHALAKE` (schemas `BRONZE SILVER GOLD SEMANTIC DOCS AUDIT`, plus `APP` for Streamlit) | `setup.sql` |
| Warehouses | `ALPHALAKE_WH_PIPELINE`, `ALPHALAKE_WH_APP` (X-Small, 60 s auto-suspend) | `setup.sql` |
| Roles | `ALPHALAKE_ENGINEER`, `ALPHALAKE_PM`, `ALPHALAKE_ANALYST` | `setup.sql` |
| Service users (key-pair only) | `SVC_ALPHALAKE_PIPELINE`, `SVC_ALPHALAKE_APP` | `setup.sql`; keys in `keys/svc_alphalake_*.p8` |
| Storage integration | `ALPHALAKE_S3_INT` ↔ IAM role `alphalake-snowflake-s3-read` (external ID `alphalake_<aws-account-id>`) | `setup.sql` / Terraform |
| Resource monitor | `ALPHALAKE_RM` (40 credits/month, suspend at 95%) | `setup.sql` |
| AWS budget | `alphalake-monthly` ($1, email alert) | Terraform creates |

Your human Snowflake login can be any name; it's only used to run `setup.sql` (and `streamlit.sql`) as `ACCOUNTADMIN`.

## 1. Snowflake trial (≈5 min)

1. Sign up at signup.snowflake.com → **Enterprise** if offered, **AWS**, **Asia Pacific (Singapore)**.
   Check the edition you actually got: if `CREATE ROW ACCESS POLICY` fails with `Unsupported feature`, it's Standard,
   so set `GOVERNANCE_MODE=views` (PII rules move into the `GOLD.DIM_CLIENT` secure view; `dbt_project.yml` already defaults to it).
2. Note the account identifier `<ORGNAME>-<ACCOUNTNAME>` (Snowsight → Admin → Accounts → hover the account → copy identifier; use a dash, not a dot).
3. The Snowflake objects themselves are created in [runbook](runbook.md) step 0 (`make snowflake-sql`, then run `infra/snowflake/setup.sql`).
4. LLM calls use `AI_COMPLETE` (new accounts can't call the legacy `SNOWFLAKE.CORTEX.COMPLETE`). Models get retired:
   `make smoke` checks `CORTEX_LLM_MODEL`; `claude-sonnet-4-5`, `claude-haiku-4-5` and `openai-gpt-5` worked on 2026-11-22
   (`openai-gpt-4.1`, `mistral-large2` and `llama4-maverick` were already retired).

## 2. AWS (≈10 min)

1. Create an AWS account (Free plan). Turn on MFA for root. Don't use root after this.
2. IAM Identity Center → enable → create a user for yourself with the `AdministratorAccess` permission set on this account.
3. Install the CLI (`brew install awscli`, or the pkg from aws.amazon.com/cli if Homebrew is stuck) and run:
   ```bash
   aws configure sso --profile alphalake     # region ap-southeast-1
   aws sts get-caller-identity --profile alphalake
   ```

## 3. Local config

```bash
make install keys                                      # venv + key pairs for the two service users
cp .env.example .env
#   SNOWFLAKE_ACCOUNT=<ORGNAME>-<ACCOUNTNAME>, AWS_ACCOUNT_ID=<12 digits>,
#   LANDING_MODE=s3 (internal = no AWS at all), GOVERNANCE_MODE=views on Standard edition
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
#   budget_email = "<you>"; snowflake_iam_user_arn is filled in at runbook step 0
```

**Snowsight Workspace:** the Workspace is git-linked to this repo and dbt there runs as a dbt Project on Snowflake,
which never reads `.env`. Keep settings dbt needs in `dbt_project.yml` (`vars`), and keep scratch worksheets
(`Untitled*.sql`) out of commits: anything containing a token makes GitHub reject the push.

Then follow the [runbook](runbook.md).

## Teardown (day 30 at the latest)

`make destroy` → in Snowsight `DROP DATABASE ALPHALAKE; DROP USER SVC_ALPHALAKE_PIPELINE; DROP USER SVC_ALPHALAKE_APP;
DROP INTEGRATION ALPHALAKE_S3_INT;` → close the AWS account
(Billing → Account → Close) and let the Snowflake trial