"""SAM-058: sam-agent serves the live HERO snapshot rm_api fetches over the network."""

from __future__ import annotations

import json
import urllib.request

from sam_worker.health import hero_snapshot_payload, start_health_server


def _get(port: int, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_hero_payload_is_a_character_sheet(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SAM_MEMORY_DB", str(tmp_path / "sam_memory.db"))
    sheet = hero_snapshot_payload()
    assert sheet["name"] == "SAMUEL"
    assert sheet["attributes"]


def test_health_server_serves_health_and_hero(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SAM_MEMORY_DB", str(tmp_path / "sam_memory.db"))
    server = start_health_server(0)
    assert server is not None
    try:
        port = server.server_address[1]
        status, health = _get(port, "/health")
        assert status == 200
        assert health["service"] == "sam-agent"

        status, sheet = _get(port, "/hero")
        assert status == 200
        assert sheet["name"] == "SAMUEL"
    finally:
        server.shutdown()
        server.server_close()
