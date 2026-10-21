"""Integration-test fixtures for the NGX SDK.

These fixtures build a real NGXClient against a live NGX Storage Array. All
integration tests are gated: they skip unless the NGX_CONTROLLERS and
NGX_API_KEY environment variables are set (see README.md).
"""

import os

import pytest

from ngxstorage import ClientConfig, NGXClient


@pytest.fixture(scope="session")
def client():
    """Return a live NGXClient, or skip the whole session when not configured."""
    controllers = os.environ.get("NGX_CONTROLLERS", "")
    api_key = os.environ.get("NGX_API_KEY", "")
    pool_name = os.environ.get("NGX_POOL_NAME", "")

    if not controllers or not api_key:
        pytest.skip(
            "integration tests need NGX_CONTROLLERS, NGX_API_KEY and "
            "NGX_POOL_NAME environment variables")

    cfg = ClientConfig(
        controllers=[c.strip() for c in controllers.split(",") if c.strip()],
        api_key=api_key,
        pool_name=pool_name,
        insecure_skip_verify=True,  # self-signed NGX Storage Array
    )
    client = NGXClient(cfg)
    # Resolve work mode + controller before any test touches the backend.
    client.refresh_controller()
    return client
