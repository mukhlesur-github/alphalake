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


def _connect_session(role: str, warehouse: str, tag: str) -> snowflake.connector.SnowflakeConnection:
    """SNOWFLAKE_AUTH=session: reuse the Snowsight sandbox's OAuth session token (its egress proxy only
    admits that token), then act as exactly `role` -- same role semantics as the key-pair path."""
    import os
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], host=os.environ["SNOWFLAKE_HOST"], authenticator="oauth",
        token=Path(os.environ.get("SNOWFLAKE_TOKEN_FILE_PATH", "/snowflake/session/token")).read_text().strip(),
        database=get_settings().snowflake_database, session_parameters={"QUERY_TAG": tag})
    cur = conn.cursor()
    for stmt in (f"USE ROLE {role}", "USE SECONDARY ROLES NONE", f"USE WAREHOUSE {warehouse}"):
        cur.execute(stmt)
    return conn


def _connect_sis(role: str) -> snowflake.connector.SnowflakeConnection:
    """SNOWFLAKE_AUTH=sis: inside Streamlit in Snowflake (warehouse runtime). The app runs with its OWNER's role
    and cannot switch, so each persona gets its own app; refuse anything else rather than run as the wrong role."""
    from snowflake.snowpark.context import get_active_session
    conn = get_active_session().connection
    # The in-Snowflake connector defaults to server-side qmark binding; our SQL uses %s / %(name)s placeholders,
    # which the connector binds (and escapes) client-side in pyformat mode.
    conn._paramstyle = "pyformat"
    current = conn.cursor().execute("SELECT CURRENT_ROLE()").fetchone()[0]
    if current != role:
        raise PermissionError(f"this app runs as {current}; open the {role} app to act as {role}")
    # Agent SQL uses SCHEMA.TABLE names. A Streamlit app already runs inside its own database (USE is not allowed
    # in its owner's-rights procedure); other in-Snowflake callers may have none, so set it only when missing.
    if conn.cursor().execute("SELECT CURRENT_DATABASE()").fetchone()[0] != get_settings().snowflake_database:
        try:
            conn.cursor().execute(f"USE DATABASE {get_settings().snowflake_database}")
        except snowflake.connector.errors.ProgrammingError:
            pass  # owner's-rights procedure: USE unsupported; the app's own database is already current
    return conn


def connect_pipeline() -> snowflake.connector.SnowflakeConnection:
    s = get_settings()
    if s.snowflake_auth == "sis":
        return _connect_sis(s.snowflake_pipeline_role)
    if s.snowflake_auth == "session":
        return _connect_session(s.snowflake_pipeline_role, s.snowflake_pipeline_warehouse, "alphalake:pipeline")
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
    if s.snowflake_auth == "sis":
        return _connect_sis(role)
    if s.snowflake_auth == "session":
        return _connect_session(role, s.snowflake_app_warehouse, f"alphalake:app:{role}")
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
