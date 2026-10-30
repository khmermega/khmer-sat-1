"""HTTP/WebSocket API tests (REQ: FR-GS-*, FR-SEC-*). The engine runs live at 10 Hz."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import make_settings

OP = {"Authorization": "Bearer op-token-for-tests"}
ADMIN = {"Authorization": "Bearer admin-token-for-tests"}


@pytest.fixture
def client(tmp_path):
    s = make_settings(tmp_path, tick_hz=10, sim_time_scale=3)
    with TestClient(create_app(s)) as c:
        _wait(lambda: c.get("/api/status").json()["onboard"]["mode"] == "NOMINAL", 10)
        yield c


def _wait(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def _cmd_status(c, cid):
    for cmd in c.get("/api/commands").json()["commands"]:
        if cmd["id"] == cid:
            return cmd["status"]
    return None


def test_health_and_status(client):
    assert client.get("/api/health").json()["status"] == "ok"
    st = client.get("/api/status").json()
    assert st["gs_mode"] == "SIMULATION"
    assert "SYNTHETIC" in st["sim"]["elements_label"]
    assert st["telemetry"]["simulated"] is True


def test_timestamps_from_database_are_explicit_utc(client):
    # Regression: SQLite drops tzinfo; browsers then parsed times as local time.
    _wait(lambda: not client.get("/api/events").json()["degraded"] and client.get("/api/events").json()["events"])
    for ev in client.get("/api/events").json()["events"]:
        assert ev["utc"].endswith("+00:00"), ev["utc"]


def test_command_requires_auth(client):
    body = {"type": "PING", "args": {}}
    assert client.post("/api/commands", json=body).status_code == 401
    assert client.post("/api/commands", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/sim/faults", json={"gnss_outage": True}).status_code == 401


def test_ping_round_trip(client):
    r = client.post("/api/commands", json={"type": "PING", "args": {}}, headers=OP)
    assert r.status_code == 202
    cid = r.json()["id"]
    assert _wait(lambda: _cmd_status(client, cid) == "COMPLETED")


def test_invalid_command_payloads(client):
    assert client.post("/api/commands", json={"type": "SELF_DESTRUCT"}, headers=OP).status_code == 422
    assert client.post("/api/commands", json={"type": "IMAGE_ACK", "args": {}}, headers=OP).status_code == 400
    assert client.post("/api/commands", json={"type": "PING", "args": {"confirm": "PING"}}, headers=OP).status_code == 400


def test_critical_command_interlock(client):
    # Direct send is refused; operators cannot arm; admin arm + execute works once.
    assert client.post("/api/commands", json={"type": "REBOOT"}, headers=OP).status_code == 409
    assert client.post("/api/commands/arm", json={"type": "REBOOT"}, headers=OP).status_code == 403
    assert client.post("/api/commands/arm", json={"type": "PING"}, headers=ADMIN).status_code == 400
    arm = client.post("/api/commands/arm", json={"type": "REBOOT"}, headers=ADMIN).json()
    r = client.post("/api/commands/execute", json={"arm_id": arm["arm_id"]}, headers=ADMIN)
    assert r.status_code == 202
    assert "confirm" not in r.json()["args"]  # interlock token is not echoed in the audit view
    assert client.post("/api/commands/execute", json={"arm_id": arm["arm_id"]}, headers=ADMIN).status_code == 409
    assert _wait(lambda: _cmd_status(client, r.json()["id"]) == "COMPLETED")


def test_capture_gallery_and_image_download(client):
    cid = client.post("/api/commands", json={"type": "CAPTURE_IMAGE", "args": {"width": 320, "height": 240}}, headers=OP).json()["id"]
    assert _wait(lambda: _cmd_status(client, cid) == "COMPLETED")
    assert _wait(lambda: len(client.get("/api/images").json()["images"]) == 1, 15)
    img = client.get("/api/images").json()["images"][0]
    assert img["source"] == "SIMULATED_ORBITAL" and img["verified"]
    f = client.get(f"/api/images/{img['id']}/file")
    assert f.status_code == 200 and f.content[:2] == b"\xff\xd8"
    assert client.get(f"/api/images/{img['id']}/thumbnail").status_code == 200
    assert client.get("/api/images/not-a-uuid/file").status_code == 400


def test_orbit_endpoints(client):
    el = client.get("/api/orbit/elements").json()
    assert el["synthetic"] is True and "NOT REAL" in el["label"]
    tr = client.get("/api/orbit/track?back_min=10&ahead_min=20&step_s=60").json()
    assert len(tr["points"]) == 31
    ps = client.get("/api/orbit/passes?hours=24").json()
    assert ps["passes"] and ps["passes"][0]["max_elevation_deg"] > 80


def test_telemetry_history_and_db_outage_fallback(client):
    _wait(lambda: client.get("/api/telemetry/history?minutes=10").json()["count"] >= 3)
    h = client.get("/api/telemetry/history?minutes=10").json()
    assert not h["degraded"] and h["count"] >= 3
    client.post("/api/sim/faults", json={"db_outage": True}, headers=OP)
    assert _wait(lambda: client.get("/api/telemetry/history?minutes=10").json()["degraded"])
    assert client.get("/api/events").json()["degraded"]
    assert _wait(lambda: client.get("/api/status").json()["database"]["ok"] is False)
    client.post("/api/sim/faults", json={"db_outage": False}, headers=OP)
    assert _wait(lambda: client.get("/api/status").json()["database"]["ok"] is True)


def test_fault_injection_validation(client):
    assert client.post("/api/sim/faults", json={"packet_loss": 2}, headers=OP).status_code == 422
    r = client.post("/api/sim/faults", json={"packet_loss": 0.2}, headers=OP).json()
    assert r["packet_loss"] == 0.2


def test_sim_control(client):
    r = client.post("/api/sim/control", json={"time_scale": 20, "link_mode": "orbital"}, headers=OP).json()
    assert r == {"time_scale": 20, "paused": False, "link_mode": "orbital"}
    assert client.post("/api/sim/control", json={"time_scale": 1000}, headers=OP).status_code == 422


def test_event_acknowledgement(client):
    ev = client.get("/api/events").json()["events"][0]
    r = client.post(f"/api/events/{ev['id']}/ack", headers=OP)
    assert r.status_code == 200 and r.json()["acknowledged_by"] == "operator"


def test_websocket_streams_ticks(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        msg = ws.receive_json()
        assert msg["type"] == "tick" and "status" in msg and "events" in msg


def test_hardware_mode_without_link(tmp_path):
    s = make_settings(tmp_path, gs_mode="HARDWARE")
    with TestClient(create_app(s)) as c:
        assert c.get("/api/status").json()["gs_mode"] == "HARDWARE"
        assert c.post("/api/commands", json={"type": "PING"}, headers=OP).status_code == 503
