from rest_framework.test import APIClient


def test_summary_requires_auth():
    c = APIClient()
    assert c.get("/api/assets/summary").status_code == 401
