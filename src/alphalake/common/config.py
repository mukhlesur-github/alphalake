"""Settings loaded from environment / .env. One object, imported everywhere."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    aws_profile: str = "alphalake"
    aws_region: str = "ap-southeast-1"
    alphalake_bucket: str = ""
    # "internal" = Snowflake internal stage + COPY task (no AWS); "s3" = S3 + Snowpipe auto-ingest
    landing_mode: str = "internal"
    # "views" = secure-view governance (any edition, matches dbt_project.yml); "policies" = masking + row access (Enterprise)
    governance_mode: str = "views"

    snowflake_account: str = ""
    snowflake_database: str = "ALPHALAKE"
    # "keypair" = service users (laptop/CI); "session" = Snowsight sandbox OAuth token + USE ROLE;
    # "sis" = Streamlit in Snowflake (the app owner's session, one app per persona)
    snowflake_auth: str = "keypair"

    snowflake_pipeline_user: str = "SVC_ALPHALAKE_PIPELINE"
    snowflake_pipeline_key: Path = Path("keys/svc_alphalake_pipeline.p8")
    snowflake_pipeline_role: str = "ALPHALAKE_ENGINEER"
    snowflake_pipeline_warehouse: str = "ALPHALAKE_WH_PIPELINE"

    snowflake_app_user: str = "SVC_ALPHALAKE_APP"
    snowflake_app_key: Path = Path("keys/svc_alphalake_app.p8")
    snowflake_app_warehouse: str = "ALPHALAKE_WH_APP"

    cortex_llm_model: str = "claude-sonnet-4-5"

    data_dir: Path = ROOT / "data"
    seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
