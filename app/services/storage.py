"""S3-compatible object storage service.

One boto3-based client speaks the S3 API to MinIO locally and Cloudflare R2 / AWS
S3 when deployed — the backend is chosen purely from env vars (blueprint §3, §9).

Rules baked in here:
- The DB stores only object **keys** (e.g. ``listings/8f2/photo1.jpg``), never
  full URLs. URLs are built at runtime via :func:`presigned_url`.
- Endpoint and credentials come from config, never hard-coded.
"""
from __future__ import annotations

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from flask import current_app


def _client():
    """Build a boto3 S3 client from the active app config."""
    cfg = current_app.config
    return boto3.client(
        "s3",
        endpoint_url=cfg.get("STORAGE_ENDPOINT_URL"),
        region_name=cfg.get("STORAGE_REGION"),
        aws_access_key_id=cfg.get("STORAGE_ACCESS_KEY"),
        aws_secret_access_key=cfg.get("STORAGE_SECRET_KEY"),
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path" if cfg.get("STORAGE_USE_PATH_STYLE") else "auto"},
        ),
    )


def _bucket_for(private: bool) -> str:
    key = "STORAGE_BUCKET_PRIVATE" if private else "STORAGE_BUCKET"
    return current_app.config[key]


def ensure_buckets() -> None:
    """Create the public + private buckets if they don't exist.

    Safe to call on startup; idempotent. Useful for a fresh MinIO container so
    the app works with no manual fiddling.
    """
    client = _client()
    for private in (False, True):
        bucket = _bucket_for(private)
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError:
            client.create_bucket(Bucket=bucket)


def upload_fileobj(fileobj, key: str, *, content_type: str | None = None,
                   private: bool = False) -> str:
    """Upload a file-like object under ``key``. Returns the stored key."""
    extra = {"ContentType": content_type} if content_type else {}
    _client().upload_fileobj(fileobj, _bucket_for(private), key, ExtraArgs=extra)
    return key


def presigned_url(key: str, *, private: bool = False, expires_in: int | None = None) -> str:
    """Build a short-lived, browser-usable URL for an object key.

    The DB only ever holds ``key``; the URL is generated on demand so servers /
    storage backends can change without touching stored data (blueprint §9).
    """
    expires_in = expires_in or current_app.config["STORAGE_PRESIGN_EXPIRY"]
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket_for(private), "Key": key},
        ExpiresIn=expires_in,
    )


def presigned_upload(key: str, *, private: bool = False, expires_in: int | None = None,
                     content_type: str | None = None) -> str:
    """Presigned PUT URL so a client can upload directly to storage."""
    expires_in = expires_in or current_app.config["STORAGE_PRESIGN_EXPIRY"]
    params = {"Bucket": _bucket_for(private), "Key": key}
    if content_type:
        params["ContentType"] = content_type
    return _client().generate_presigned_url(
        "put_object", Params=params, ExpiresIn=expires_in
    )


def delete_object(key: str, *, private: bool = False) -> None:
    _client().delete_object(Bucket=_bucket_for(private), Key=key)
