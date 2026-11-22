"""Sync data/landing -> s3://<bucket>/landing (skips objects that already exist with the same size).

S3 ObjectCreated -> Snowflake's SQS queue -> Snowpipe auto-ingest. No AWS keys in Snowflake:
the stage uses the storage integration's IAM role.
"""

from pathlib import Path

from alphalake.common.config import get_settings


def s3_client():
    import boto3
    s = get_settings()
    return boto3.Session(profile_name=s.aws_profile, region_name=s.aws_region).client("s3")


def put_internal(cur, f: Path, key: str) -> None:
    """PUT one file to the internal stage keeping the S3 key layout (key is relative to landing/).

    LANDING_MODE=internal: @BRONZE.LANDING is that internal stage. LANDING_MODE=s3 without AWS credentials
    (e.g. the Snowsight sandbox): PUT to @BRONZE.LANDING_INTERNAL, then let Snowflake COPY FILES it into the
    S3 stage @BRONZE.LANDING, whose bucket notification triggers Snowpipe."""
    folder = key.rsplit("/", 1)[0]
    s3 = get_settings().landing_mode == "s3"
    stage = "ALPHALAKE.BRONZE.LANDING_INTERNAL" if s3 else "ALPHALAKE.BRONZE.LANDING"
    cur.execute(f"PUT 'file://{f.as_posix()}' '@{stage}/{folder}/' AUTO_COMPRESS = FALSE OVERWRITE = FALSE")
    if s3:
        cur.execute("COPY FILES INTO @ALPHALAKE.BRONZE.LANDING FROM @ALPHALAKE.BRONZE.LANDING_INTERNAL "
                    "FILES = (%s) DETAILED_OUTPUT = FALSE", (key,))


def upload_internal(prefix: str = "") -> None:
    """LANDING_MODE=internal: same files, PUT to the internal stage. OVERWRITE=FALSE skips existing names."""
    from alphalake.common.snowflake import connect_pipeline
    s = get_settings()
    root = s.data_dir / "landing"
    cur = connect_pipeline().cursor()
    sent = 0
    for f in sorted((root / prefix).rglob("*") if prefix else root.rglob("*")):
        if f.is_file():
            put_internal(cur, f, f.relative_to(root).as_posix())
            sent += 1
    print(f"PUT {sent} file(s) -> @ALPHALAKE.BRONZE.LANDING/{prefix} (existing names skipped)")


def upload(prefix: str = "") -> None:
    s = get_settings()
    # internal mode, or s3 mode from a sandbox that only reaches Snowflake: relay through the internal stage
    if s.landing_mode != "s3" or s.snowflake_auth == "session":
        return upload_internal(prefix)
    if not s.alphalake_bucket:
        raise SystemExit("ALPHALAKE_BUCKET is empty -- run `make tf-output` first")
    root = s.data_dir / "landing"
    s3 = s3_client()
    existing = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=s.alphalake_bucket, Prefix=f"landing/{prefix}"):
        existing.update({o["Key"]: o["Size"] for o in page.get("Contents", [])})
    sent = skipped = 0
    for f in sorted((root / prefix).rglob("*") if prefix else root.rglob("*")):
        if not f.is_file():
            continue
        key = "landing/" + f.relative_to(root).as_posix()
        if existing.get(key) == f.stat().st_size:
            skipped += 1
            continue
        s3.upload_file(str(f), s.alphalake_bucket, key)
        sent += 1
    # Raw PDFs go alongside for lineage (not loaded by Snowpipe; parsed JSON is)
    if not prefix or prefix.startswith("docs"):
        for f in sorted((s.data_dir / "docs" / "raw").glob("*.pdf")):
            s3.upload_file(str(f), s.alphalake_bucket, f"raw/docs/{f.name}")
    print(f"uploaded {sent}, skipped {skipped} unchanged -> s3://{s.alphalake_bucket}/landing/{prefix}")
