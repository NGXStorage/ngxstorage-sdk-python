"""Unified NGX Storage Manager API v2 SDK.

This package mirrors the Go SDK (ngx-sdk-go): one client, one auth/retry/
failover implementation, and per-resource services covering every API v2
group. The API key and any CHAP/S3 secret are never logged.
"""

from ngxstorage.client import NGXClient, ClientConfig
from ngxstorage.errors import APIError, PoolNotFound, ClusterNotReady

__all__ = ["NGXClient", "ClientConfig", "APIError", "PoolNotFound", "ClusterNotReady"]
__version__ = "1.0.0"
