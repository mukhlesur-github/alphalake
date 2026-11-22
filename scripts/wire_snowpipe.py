"""Close the Snowpipe loop: read the account's Snowpipe SQS ARN and re-apply Terraform with it,
so S3 ObjectCreated events under landing/ reach every auto-ingest pipe."""

import subprocess

from alphalake.common.config import ROOT
from alphalake.common.snowflake import connect_pipeline

cur = connect_pipeline().cursor()
cur.execute("SHOW PIPES IN SCHEMA ALPHALAKE.BRONZE")
cols = [c[0] for c in cur.description]
arns = {dict(zip(cols, r))["notification_channel"] for r in cur.fetchall()}
arns.discard(None)
assert len(arns) == 1, f"expected one notification channel, got {arns}"
arn = arns.pop()
print(f"Snowpipe SQS: {arn}")
subprocess.run(["terraform", "apply", "-auto-approve", f"-var=snowpipe_sqs_arn={arn}"],
               cwd=ROOT / "infra/terraform", check=True)
(ROOT / "infra/terraform/snowpipe.auto.tfvars").write_text(f'snowpipe_sqs_arn = "{arn}"\n')
print("bucket notification -> Snowpipe wired (saved to infra/terraform/snowpipe.auto.tfvars)")
