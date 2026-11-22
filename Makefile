# AlphaLake -- run `make help`. Values from .env are exported to every recipe.
SHELL := /bin/bash
-include .env
export
TF := terraform -chdir=infra/terraform
DBT := cd dbt && DBT_PRIVATE_KEY_PATH=$(CURDIR)/$(SNOWFLAKE_PIPELINE_KEY) uv run --group dbt dbt
PY := uv run

.PHONY: help
help:  ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

# ---- local (no accounts needed) -------------------------------------------------------
install:  ## python 3.12 venv + all deps
	uv sync --group dev --group dbt
keys:  ## generate RSA key pairs for the 3 service users (keys/, git-ignored)
	scripts/gen_keys.sh
generate:  ## synthetic batch data + trade history -> data/landing
	$(PY) alphalake generate
docs:  ## synthetic PDFs -> parse -> chunked JSON (SHA-256 incremental)
	$(PY) alphalake generate-docs && $(PY) alphalake parse-docs
test:  ## unit tests (generators, parser, metric compiler, SQL guard, agent graph)
	$(PY) pytest -q
lint:
	$(PY) ruff check src tests app

# ---- one-time account wiring ------------------------------------------------------------
snowflake-sql:  ## render infra/snowflake/setup.sql (roles, warehouses, users, integration) to run as ACCOUNTADMIN
	$(PY) python scripts/render_snowflake_setup.py
tf-init:
	$(TF) init
tf-plan:  ## terraform plan (AWS + Snowflake)
	$(TF) plan
tf-apply:  ## AWS only: bucket, IAM role (trusts ALPHALAKE_S3_INT), budget
	$(TF) apply
	$(PY) python scripts/set_env_from_tf.py
migrate:  ## apply snowflake/migrations (stage, pipes, streams, tasks, procs, search services)
	$(PY) alphalake migrate
wire-snowpipe:  ## second terraform apply: S3 notifications -> Snowpipe SQS
	$(PY) python scripts/wire_snowpipe.py
smoke:  ## check every integration handshake
	$(PY) alphalake smoke

# ---- run the platform --------------------------------------------------------------------
upload:  ## push data/landing to S3 (Snowpipe auto-ingests)
	$(PY) alphalake upload
backfill:  ## load files already landed (S3 pipes or internal COPY), then run tasks now
ifeq ($(LANDING_MODE),s3)
	$(PY) python scripts/run_sql.py snowflake/ops/backfill_pipes.sql
	sleep 60
	$(PY) python scripts/run_sql.py snowflake/ops/run_tasks_now.sql
else
	$(PY) python scripts/run_sql.py snowflake/ops/backfill_internal.sql
endif
status:  ## row counts per layer
	$(PY) python scripts/run_sql.py snowflake/ops/status.sql
stream:  ## live trades for 2 minutes (RATE trades/sec)
	$(PY) alphalake stream --rate $${RATE:-5} --seconds $${SECONDS_:-120}
dbt-build:  ## dbt snapshot + models + tests, then the semantic view
	$(DBT) build --profiles-dir . --vars '{governance_mode: $(or $(GOVERNANCE_MODE),policies)}'
	$(DBT) run-operation create_semantic_view --profiles-dir .
dbt-docs:
	$(DBT) docs generate --profiles-dir . && $(DBT) docs serve --profiles-dir .
verify:  ## live SQL assertions (SCD2 idempotency, CDC, stale chunks, retrieval, flagship number)
	$(PY) python scripts/run_sql.py snowflake/ops/verify.sql
ask:  ## make ask Q="..." ROLE=ALPHALAKE_ANALYST MODE=sql
	$(PY) alphalake ask "$(Q)" --role $${ROLE:-ALPHALAKE_PM} --mode $${MODE:-tool}
app:  ## Streamlit app on localhost:8501
	$(PY) streamlit run app/streamlit_app.py

# ---- teardown ------------------------------------------------------------------------------
destroy:  ## delete everything Terraform created (bucket is force-emptied)
	$(TF) destroy
