"""Shared fixtures for the SDK unit tests."""

import time

import pytest

from ngxstorage import ClientConfig, NGXClient


@pytest.fixture
def client():
    c = NGXClient(ClientConfig(controllers=["10.0.0.1"], api_key="test-key", pool_name="pool1"))
    # Simulate a completed initial refresh (as drivers perform at startup) so
    # per-request _ensure_refresh does not fire during unit tests.
    c._last_refresh = time.time()
    return c
