"""AWSBackend — AWS Secrets Manager via boto3."""

from __future__ import annotations

import json
import logging
import os

from huawei_manager.vault_backends.base import SecretsBackend

log = logging.getLogger("huawei.vault")


class AWSBackend(SecretsBackend):
    """AWS Secrets Manager via boto3. Requer: pip install boto3"""

    def __init__(self) -> None:
        try:
            import boto3  # pyright: ignore[reportMissingImports]
            self._boto3 = boto3
        except ImportError:
            raise RuntimeError("boto3 não instalado: pip install boto3")

        region = os.getenv("AWS_REGION", "us-east-1")
        self._secret_name = os.getenv("AWS_SECRET_NAME", "huawei/manager/creds")
        self._client = boto3.client("secretsmanager", region_name=region)
        self._cache: dict = {}
        self._refresh()
        log.debug("AWS Secrets Manager: %s  region=%s", self._secret_name, region)

    def _refresh(self) -> None:
        resp = self._client.get_secret_value(SecretId=self._secret_name)
        self._cache = json.loads(resp["SecretString"])

    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)

    def put(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._client.update_secret(
            SecretId=self._secret_name,
            SecretString=json.dumps(self._cache),
        )

    @property
    def backend_name(self) -> str:
        return "AWS Secrets Manager"
