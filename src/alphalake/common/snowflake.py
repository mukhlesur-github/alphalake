"""Snowflake connections with key-pair auth.

Two identities:
  * pipeline -> SVC_ALPHALAKE_PIPELINE / ALPHALAKE_ENGINEER (migrations, loads, dbt)
  * app      -> SVC_ALPHALAKE_APP, which is granted the persona roles and runs every
                agent query under the *end user's* role (role inheritance).
"""

from contextlib import contextmanager
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization

from alphalake.common.config import ROOT, get_settings

PERSONA_ROLES = ("ALPHALAKE_PM", "ALPHALAKE_ANALYST")


def _private_key_der(path: Path) -> bytes:
    path = path if path.is_absolute() else ROOT / path
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def connect_pipeline() -> snowflake.connector.SnowflakeConnection:
    s = get_settings()
    return snowflake.connector.connect(
        account=s.snowflake_account,
        user=s.snowflake_pipeline_user,
        private_key=_private_key_der(s.snowflake_pipeline_key),
        role=s.snowflake_pipeline_role,
        warehouse=s.snowflake_pipeline_warehouse,
        database=s.snowflake_database,
        session_parameters={"QUERY_TAG": "alphalake:pipeline"},
    )


def connect_as_persona(role: str) -> snowflake.connector.SnowflakeConnection:
    """Connect as the app service user, then act *only* as the persona role.

    Secondary roles are disabled so masking / row-access policies and grants see exactly
    one role -- otherwise a service user holding several persona roles would see the
    union of their privileges.
    """
    if role not in PERSONA_ROLES:
        raise ValueError(f"unknown persona role {role!r}")
    s = get_settings()
    conn = snowflake.connector.connect(
        account=s.snowflake_account,
        user=s.snowflake_app_user,
        private_key=_private_key_der(s.snowflake_app_key),
        role=role,
        warehouse=s.snowflake_app_warehouse,
        database=s.snowflake_database,
        session_parameters={"QUERY_TAG": f"alphalake:app:{role}"},
    )
    conn.cursor().execute("USE SECONDARY ROLES NONE")
    return conn


@contextmanager
def cursor(conn):
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        yield cur
    finally:
        cur.close()
