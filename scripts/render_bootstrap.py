"""Render infra/bootstrap/bootstrap.sql with the Terraform user's public key inlined."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
pub = (root / "keys/svc_alphalake_terraform.pub").read_text().splitlines()
body = "".join(line for line in pub if not line.startswith("-----"))
tmpl = (root / "infra/bootstrap/bootstrap.sql.tmpl").read_text()
out = root / "infra/bootstrap/bootstrap.sql"
out.write_text(tmpl.replace("{{TF_PUBKEY}}", body))
print(f"wrote {out.relative_to(root)} -- paste it into a Snowsight worksheet and run all")
