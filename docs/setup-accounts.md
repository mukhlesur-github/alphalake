# Account Setup (MVP, $0)

Everything below uses the **exact names the code expects**. Never paste secrets or private keys into chat or git:
they live in `.env` and `keys/` (both git-ignored).

## Names at a glance

| Thing | Value | Where it's used |
|---|---|---|
| AWS region | `us-west-2` (Oregon) | `.env` `AWS_REGION`, `terraform.tfvars` |
| AWS CLI profile | `alphalake` | `.env` `AWS_PROFILE`, Terraform provider |
| S3 bucket | `alphalake-landing-<your-aws-account-id>` (Terraform creates it) | auto-written to `.env` |
| Snowflake edition / cloud / region | **Enterprise**, **AWS**, **US West (Oregon)** | trial signup |
| Snowflake account identifier | `<ORGNAME>-<ACCOUNTNAME>` (Snowsight → Admin → Accounts) | `.env` `SNOWFLAKE_ACCOUNT`, `terraform.tfvars` |
| Snowflake database | `ALPHALAKE` (schemas `BRONZE SILVER GOLD SEMANTIC DOCS AUDIT`) | Terraform creates |
| Warehouses | `ALPHALAKE_WH_PIPELINE`, `ALPHALAKE_WH_APP` (X-Small, 60 s auto-suspend) | Terraform creates |
| Roles | `ALPHALAKE_ENGINEER`, `ALPHALAKE_PM`, `ALPHALAKE_ANALYST` | Terraform creates |
| Service users (key-pair only) | `SVC_ALPHALAKE_TERRAFORM` (you create, bootstrap), `SVC_ALPHALAKE_PIPELINE`, `SVC_ALPHALAKE_APP` (Terraform) | `keys/svc_alphalake_*.p8` |
| Storage integration | `ALPHALAKE_S3_INT` ↔ IAM role `alphalake-snowflake-s3-read` | Terraform creates both sides |
| Resource monitor | `ALPHALAKE_RM` (40 credits/month, suspend at 95%) | Terraform creates |
| AWS budget | `alphalake-monthly` ($1, email alert) | Terraform creates |

Your human Snowflake login can be any name; it's only used once to run the bootstrap SQL.

## 1. Snowflake trial (≈5 min)

1. Sign up at signup.snowflake.com → **Enterprise**, **AWS**, **US West (Oregon)**.
2. Note the account identifier `<ORGNAME>-<ACCOUNTNAME>` (Snowsight → Admin → Accounts → hover the account → copy identifier; use a dash, not a dot).
3. Run `make bootstrap-sql` locally, open `infra/bootstrap/bootstrap.sql`, paste it into a Snowsight worksheet, **Run All** as `ACCOUNTADMIN`.
   It creates `SVC_ALPHALAKE_TERRAFORM` with your public key, enables Cortex cross-region, and checks that `EMBED_TEXT_1024` and `COMPLETE` work.
   - If the `COMPLETE` check fails for `openai-gpt-4.1`, try `claude-sonnet-4-5`, `llama3.3-70b` or `mistral-large2`, and put the working name in `.env` `CORTEX_LLM_MODEL`.

## 2. AWS (≈10 min)

1. Create an AWS account (Free plan). Turn on MFA for root. Don't use root after this.
2. IAM Identity Center → enable → create a user for yourself with the `AdministratorAccess` permission set on this account.
3. Install the CLI (`brew install awscli`, or the pkg from aws.amazon.com/cli if Homebrew is stuck) and run:
   ```bash
   aws configure sso --profile alphalake     # region us-west-2
   aws sts get-caller-identity --profile alphalake
   ```

## 3. Local config

```bash
cp .env.example .env                                   # set SNOWFLAKE_ACCOUNT=<ORGNAME>-<ACCOUNTNAME>
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
#   snowflake_organization_name = "<ORGNAME>", snowflake_account_name = "<ACCOUNTNAME>", budget_email = "<you>"
```

Already done for you on this machine: Python 3.12 venv (`uv`), Terraform 1.17 in `~/.local/bin`, key pairs in `keys/`.

Then follow the [runbook](runbook.md).

## Teardown (day 30 at the latest)

`make destroy` → in Snowsight `DROP DATABASE ALPHALAKE; DROP USER SVC_ALPHALAKE_TERRAFORM;` → close the AWS account
(Billing → Account → Close) and let the Snowflake trial expire.
