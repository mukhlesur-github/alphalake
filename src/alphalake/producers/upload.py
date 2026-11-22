"""Sync data/landing -> s3://<bucket>/landing (skips objects that already exist with the same size).

S3 ObjectCreated -> Snowflake's SQS queue -> Snowpipe auto-ingest. No AWS keys in Snowflake:
the stage uses the storage integration's IAM role.
"""

import boto3

from alphalake.common.config import get_settings


def s3_client():
    s = get_settings()
    return boto3.Session(profile_name=s.aws_profile, region_name=s.aws_region).client("s3")


def upload(prefix: str = "") -> None:
    s = get_settings()
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
