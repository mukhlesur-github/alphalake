"""Settings loaded from environment / .env. One object, imported everywhere."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    aws_profile: str = "alphalake"
    aws_region: str = "us-west-2"
    alphalake_bucket: str = ""

    snowflake_account: str = ""
    snowflake_database: str = "ALPHALAKE"

    snowflake_pipeline_user: str = "SVC_ALPHALAKE_PIPELINE"
    snowflake_pipeline_key: Path = Path("keys/svc_alphalake_pipeline.p8")
    snowflake_pipeline_role: str = "ALPHALAKE_ENGINEER"
    snowflake_pipeline_warehouse: str = "ALPHALAKE_WH_PIPELINE"

    snowflake_app_user: str = "SVC_ALPHALAKE_APP"
    snowflake_app_key: Path = Path("keys/svc_alphalake_app.p8")
    snowflake_app_warehouse: str = "ALPHALAKE_WH_APP"

    cortex_llm_model: str = "openai-gpt-4.1"

    data_dir: Path = ROOT / "data"
    seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
