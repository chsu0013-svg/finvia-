import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from auth import current_user  # noqa: E402


@pytest.fixture()
def anon(tmp_path, monkeypatch):
    """A visitor who is NOT signed in."""
    monkeypatch.setattr(main, "UPLOADS", tmp_path)
    main._sessions.clear()
    main.app.dependency_overrides.clear()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture()
def who():
    """Which fake user is signed in. Change who['id'] to switch users."""
    return {"id": "user-a"}


@pytest.fixture()
def client(anon, who):
    """A visitor who IS signed in (fake Supabase user, no real login needed)."""
    main.app.dependency_overrides[current_user] = lambda: {
        "id": who["id"],
        "email": f"{who['id']}@example.com",
    }
    return anon


CSV = (
    "Date,Description,Debit,Credit,Balance\n"
    "01/09/2026,Customer payment,,12000,52000\n"
    "05/09/2026,Laptop purchase,2400,,49600\n"
    "09/09/2026,Cloud hosting subscription,860,,48740\n"
    "12/09/2026,Payroll,9500,,39240\n"
)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/health").json()["status"] == "ok"


def test_frontend_served_with_brand_assets(client):
    r = client.get("/")
    assert r.status_code == 200 and "Finvia" in r.text
    for path in ("/app.css", "/app.js", "/manifest.webmanifest", "/icon-512.png", "/icon-192.png", "/service-worker.js"):
        assert client.get(path).status_code == 200, path
    assert "#dfeeff" in client.get("/app.css").text


@pytest.mark.parametrize(
    "path",
    ["/main.py", "/analysis.py", "/Dockerfile", "/requirements.txt", "/backend/main.py", "/../backend/main.py", "/uploads/", "/.github/workflows/deploy-ecs-express.yml"],
)
def test_source_and_uploads_not_exposed(client, path):
    r = client.get(path)
    assert r.status_code == 404 or "FastAPI" not in r.text
    assert "import os" not in r.text


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]


# ---------- Login rules ----------
def test_api_requires_sign_in(anon):
    assert anon.get("/api/dashboard").status_code == 401
    assert anon.get("/api/tax-report").status_code == 401
    r = anon.post("/api/upload", files={"file": ("stmt.csv", io.BytesIO(CSV.encode()), "text/csv")})
    assert r.status_code == 401
    assert anon.post("/api/referral", json={"consent": True}).status_code == 401


def test_me_requires_sign_in(anon):
    assert anon.get("/api/auth/me").status_code == 401


def test_register_rejects_bad_email(anon):
    r = anon.post("/api/auth/register", json={"email": "not-an-email", "password": "secret123"})
    assert r.status_code == 400


def test_register_rejects_short_password(anon):
    r = anon.post("/api/auth/register", json={"email": "a@example.com", "password": "123"})
    assert r.status_code == 400


# ---------- API (signed in) ----------
def test_demo_dashboard_shape(client):
    d = client.get("/api/dashboard").json()
    assert len(d["balances"]) == 31 and d["start"] == 48600
    assert min(d["balances"]) == 11150  # matches the gap shown in the UI


def test_upload_csv_and_tax_signals(client):
    r = client.post("/api/upload", files={"file": ("stmt.csv", io.BytesIO(CSV.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Analysed 4 transactions" in body["message"]
    titles = {s["title"] for s in body["dashboard"]["signals"] if s["type"] == "tax"}
    assert {"Equipment purchase", "Software subscriptions"} <= titles
    assert client.get("/api/tax-report").json()["items"]


def test_workspaces_are_private_per_user(client, who):
    # User A uploads a statement.
    client.post("/api/upload", files={"file": ("stmt.csv", io.BytesIO(CSV.encode()), "text/csv")})
    assert client.get("/api/dashboard").json()["start"] == 39240
    # User B is a different signed-in user: gets a fresh workspace.
    who["id"] = "user-b"
    assert client.get("/api/dashboard").json()["start"] == 48600
    # Back to user A: their upload is still there.
    who["id"] = "user-a"
    assert client.get("/api/dashboard").json()["start"] == 39240


def test_upload_rejects_bad_type(client):
    r = client.post("/api/upload", files={"file": ("evil.exe", io.BytesIO(b"x"), "application/octet-stream")})
    assert r.status_code == 400


def test_upload_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 1024)
    r = client.post("/api/upload", files={"file": ("big.csv", io.BytesIO(b"a" * 5000), "text/csv")})
    assert r.status_code == 413
    assert list(main.UPLOADS.iterdir()) == []  # partial file cleaned up


def test_bad_csv_does_not_crash(client):
    r = client.post("/api/upload", files={"file": ("x.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")})
    assert r.status_code == 200 and "Could not analyse" in r.json()["message"]


def test_referral_requires_consent(client):
    assert client.post("/api/referral", json={"consent": False}).status_code == 400
    assert client.post("/api/referral", json={"consent": True}).json()["status"] == "submitted"
