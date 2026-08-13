import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Return a DRF APIClient instance for use in tests."""
    return APIClient()
