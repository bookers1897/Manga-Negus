import os
import pytest

from manganegus_app import create_app


@pytest.fixture(scope="module")
def client():
    # Keep tests lightweight: no source discovery or Playwright
    os.environ["SKIP_SOURCE_DISCOVERY"] = "1"
    os.environ["SKIP_PLAYWRIGHT_SOURCES"] = "1"
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    app = create_app()
    with app.test_client() as client:
        yield client


def test_index_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Manga" in resp.data


def test_csrf_token(client):
    resp = client.get("/api/csrf-token")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "csrf_token" in data
    assert isinstance(data["csrf_token"], str)
    assert len(data["csrf_token"]) > 0


def test_sources_health(client):
    resp = client.get("/api/sources/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "sources" in data
    assert "available_count" in data
