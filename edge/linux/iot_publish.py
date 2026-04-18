"""
Publishes classification events directly to S3 as partitioned JSON objects.

Key pattern:  raw/YYYY/MM/DD/<thing_name>_<HHMMSSffffff>.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.config import Config as BotoConfig

log = logging.getLogger(__name__)


class IotPublisher:
    def __init__(self, bucket: str, thing_name: str, region: str = "us-east-1"):
        self._bucket = bucket
        self._thing = thing_name
        self._s3 = boto3.client(
            "s3",
            region_name=region,
            config=BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
        )

    def publish(self, event: dict) -> None:
        ts = datetime.now(timezone.utc)
        key = (
            f"raw/{ts.year:04d}/{ts.month:02d}/{ts.day:02d}/"
            f"{self._thing}_{ts.strftime('%H%M%S%f')}.json"
        )
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=json.dumps(event, default=str).encode(),
                ContentType="application/json",
            )
            log.info("Published → s3://%s/%s", self._bucket, key)
        except Exception as exc:
            log.error("S3 publish failed: %s", exc)
