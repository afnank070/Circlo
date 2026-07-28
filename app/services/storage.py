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


def _client(*, public: bool = False):
    """Build a boto3 S3 client from the active app config.

    ``public=True`` signs against ``STORAGE_PUBLIC_URL`` (the browser-facing base,
    e.g. ``http://localhost:9000`` in dev or an R2 domain in prod) so that
    presigned URLs handed to a browser carry a host the browser can actually
    reach. Server-side calls (uploads, bucket setup) use the internal endpoint.
    Falls back to the internal endpoint when no public URL is configured, so
    behaviour is unchanged if the var is unset.
    """
    cfg = current_app.config
    endpoint = cfg.get("STORAGE_ENDPOINT_URL")
    if public and cfg.get("STORAGE_PUBLIC_URL"):
        endpoint = cfg.get("STORAGE_PUBLIC_URL")

    # R2 requires virtual-hosted style addressing; MinIO requires path style.
    is_r2 = "r2.cloudflarestorage.com" in (cfg.get("STORAGE_ENDPOINT_URL") or "")
    if is_r2:
        addressing_style = "virtual"
    elif cfg.get("STORAGE_USE_PATH_STYLE"):
        addressing_style = "path"
    else:
        addressing_style = "auto"

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=cfg.get("STORAGE_REGION"),
        aws_access_key_id=cfg.get("STORAGE_ACCESS_KEY"),
        aws_secret_access_key=cfg.get("STORAGE_SECRET_KEY"),
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": addressing_style},
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
    """Build a browser-usable URL for an object key.

    The DB only ever holds ``key``; the URL is generated on demand so servers /
    storage backends can change without touching stored data (blueprint §9).

    An R2 ``.r2.dev`` public bucket URL is already the final, bucket-specific
    host and serves objects unauthenticated — it doesn't accept a signature or
    a bucket subdomain prefix. So for the public bucket, when
    ``STORAGE_PUBLIC_URL`` is an r2.dev domain, build the URL directly instead
    of presigning. Private objects always go through a real presigned request
    against the storage API endpoint.
    """
    public_url = current_app.config.get("STORAGE_PUBLIC_URL")
    if not private and public_url and ".r2.dev" in public_url:
        return f"{public_url.rstrip('/')}/{key}"

    expires_in = expires_in or current_app.config["STORAGE_PRESIGN_EXPIRY"]
    return _client(public=True).generate_presigned_url(
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
    return _client(public=True).generate_presigned_url(
        "put_object", Params=params, ExpiresIn=expires_in
    )


def delete_object(key: str, *, private: bool = False) -> None:
    _client().delete_object(Bucket=_bucket_for(private), Key=key)
