"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient
from mock_tools.app import app as mock_tools_app


@pytest.fixture
def tools_http():
    with TestClient(mock_tools_app) as client:
        yield client
