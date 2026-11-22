"""Write Terraform outputs (bucket name) into .env."""

import json
import re
import subprocess

from alphalake.common.config import ROOT

out = json.loads(subprocess.run(["terraform", "output", "-json"], cwd=ROOT / "infra/terraform",
                                check=True, capture_output=True, text=True).stdout)
env = ROOT / ".env"
text = env.read_text()
text = re.sub(r"^ALPHALAKE_BUCKET=.*$", f"ALPHALAKE_BUCKET={out['bucket']['value']}", text, flags=re.M)
env.write_text(text)
print(f"ALPHALAKE_BUCKET={out['bucket']['value']} -> .env")
