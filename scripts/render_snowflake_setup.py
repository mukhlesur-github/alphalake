"""Render infra/snowflake/setup.sql with the service users' public keys and the AWS account id inlined."""

import os
from pathlib import Path

from jinja2 import Template

root = Path(__file__).resolve().parents[1]


def pubkey(user: str) -> str:
    lines = (root / f"keys/svc_alphalake_{user}.pub").read_text().splitlines()
    return "".join(line for line in lines if not line.startswith("-----"))


aws_account_id = os.environ.get("AWS_ACCOUNT_ID", "")
if not (aws_account_id.isdigit() and len(aws_account_id) == 12):
    raise SystemExit("set AWS_ACCOUNT_ID (12 digits) in .env")
tmpl = Template((root / "infra/snowflake/setup.sql.tmpl").read_text())
out = root / "infra/snowflake/setup.sql"
out.write_text(tmpl.render(pipeline_pubkey=pubkey("pipeline"), app_pubkey=pubkey("app"), aws_account_id=aws_account_id))
print(f"wrote {out.relative_to(root)} -- run it in Snowsight as ACCOUNTADMIN")
