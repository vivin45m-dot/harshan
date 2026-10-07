import pytest

from foodtrace.config import ARTIFACTS_DIR, LEDGER_DB

pytestmark = pytest.mark.skipif(
    not (ARTIFACTS_DIR / "evidential.pt").exists() or not LEDGER_DB.exists(),
    reason="needs a trained model and ledger (run pipeline.ps1)")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from foodtrace.api.main import app
    return TestClient(app)


def test_overview(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    assert r.json()["nodes"] > 0


def test_node_detail_has_forecast_and_uncertainty(client):
    node = client.get("/api/nodes").json()["nodes"][0]["node_id"]
    d = client.get(f"/api/nodes/{node}").json()
    nx = d["next"]
    assert nx["forecast_kg"] >= 0 and nx["epistemic"] > 0 and nx["aleatoric"] > 0
    assert nx["lo80_kg"] <= nx["forecast_kg"] <= nx["hi80_kg"]


def test_tamper_then_restore(client):
    assert client.get("/api/ledger/verify").json()["valid"]
    block = client.get("/api/ledger/blocks?limit=1").json()["blocks"][0]["idx"]
    rec = client.get(f"/api/ledger/blocks/{block}?kind=shipment").json()["records"][0]
    broken = client.post("/api/ledger/tamper", json={"record_id": rec["id"], "field": "qty_kg", "value": 1}).json()
    assert not broken["valid"]
    assert broken["problems"][0]["block_index"] == block
    assert client.post("/api/ledger/restore").json()["valid"]
