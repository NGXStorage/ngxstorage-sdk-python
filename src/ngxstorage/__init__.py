"""Unified NGX Storage Manager API v2 SDK.

One client, one auth/retry/failover implementation, and per-resource services
for the API v2 groups with current consumers and verified contracts. The API
key and any CHAP/S3 secret are never logged.
"""

from ngxstorage.client import NGXClient, ClientConfig
from ngxstorage.errors import APIError, PoolNotFound, ClusterNotReady

__all__ = ["NGXClient", "ClientConfig", "APIError", "PoolNotFound", "ClusterNotReady"]
__version__ = "1.0.0"
