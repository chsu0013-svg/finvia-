import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UPLOADS", tmp_path)
    main._sessions.clear()
    return TestClient(main.app)


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


def test_workspaces_are_private_per_visitor(client):
    client.post("/api/upload", files={"file": ("stmt.csv", io.BytesIO(CSV.encode()), "text/csv")})
    assert client.get("/api/dashboard").json()["start"] == 39240
    other = TestClient(main.app)  # no cookie -> its own fresh workspace
    assert other.get("/api/dashboard").json()["start"] == 48600


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
