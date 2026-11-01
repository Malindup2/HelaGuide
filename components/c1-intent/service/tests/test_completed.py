"""Completed requests saved to SQLite (app/core/completed.py) and GET /v1/requests/completed.

Uses the fake engine (tests/conftest.py); nic_lost_in_badulla fills district and urgency, so the request is ready.
"""
import logging
import sqlite3

from app.core import completed, pipeline
from app.core.completed import CompletedStore

from tests.test_intent_policy import Chat
from tests.test_multi_requests import nic_lost_in_badulla

NIC_SLOTS = {"district": "Badulla", "urgency": "urgent"}


def saved(client, **params):
    r = client.get("/v1/requests/completed", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_nothing_is_saved_before_the_request_is_ready(client, real_mode):
    d = nic_lost_in_badulla(real_mode, Chat(client), urgent=False)
    assert d["ready"] is False
    assert saved(client) == []


def test_ready_request_is_saved_with_when_it_completed(client, real_mode):
    d = nic_lost_in_badulla(real_mode, Chat(client, "anon-done"))
    assert d["ready"] is True
    [row] = saved(client)
    assert {k: row[k] for k in ("session_id", "endpoint", "intent", "service_id", "slots", "conditions", "turn_id")} \
        == {"session_id": "anon-done", "endpoint": "intent", "intent": "nic_replace_lost", "service_id": "svc:nic",
            "slots": NIC_SLOTS, "conditions": {}, "turn_id": d["turn_id"]}
    assert row["completed_at"] == row["updated_at"]
    assert row["completed_at"].endswith("Z") or row["completed_at"].endswith("+00:00")


def test_later_turns_keep_the_first_completion(client, real_mode, completed_db):
    chat = Chat(client)
    nic_lost_in_badulla(real_mode, chat)
    first = saved(client)[0]
    real_mode["hari"] = ("nic_replace_lost", 0.6)
    chat.say("hari")
    assert saved(client) == [first]         # same slots: no new row, no new time


def test_a_correction_updates_the_slots_but_not_completed_at(real_mode, tmp_path):
    times = iter(["2026-10-22T09:00:00+00:00", "2026-10-22T09:05:00+00:00"])
    store = CompletedStore(tmp_path / "c.sqlite3", clock=lambda: next(times))
    state = {"turn_id": 2, "ready": True, "active_intent": "nic_replace_lost", "slots": dict(NIC_SLOTS),
             "conditions": {}, "completed_requests": []}
    assert store.record("anon-1", "intent", state) == 1
    assert store.record("anon-1", "intent", {**state, "turn_id": 3, "slots": {**NIC_SLOTS, "district": "Galle"}}) == 1
    [row] = store.list()
    assert (row["slots"]["district"], row["turn_id"]) == ("Galle", 2)
    assert (row["completed_at"], row["updated_at"]) == ("2026-10-22T09:00:00+00:00", "2026-10-22T09:05:00+00:00")


def test_switching_service_keeps_the_finished_request(client, real_mode):
    chat = Chat(client)
    nic_lost_in_badulla(real_mode, chat)
    text = "passport ekakuth ganna one"
    real_mode[text] = ("nic_replace_lost", 0.8)
    real_mode[("current", text)] = ("passport_new", 0.7)
    assert chat.say(text)["active_intent"] == "passport_new"
    assert [r["intent"] for r in saved(client)] == ["nic_replace_lost"]


def test_chat_endpoint_saves_too_and_filters_work(client, real_mode, monkeypatch):
    monkeypatch.delenv("C1_DIALOGUE_MODE", raising=False)
    nic_lost_in_badulla(real_mode, Chat(client, "anon-a"))
    for text in ("mage ID eka nathi una", "Badulla", "ikmanata one"):
        r = client.post("/v1/chat", json={"session_id": "anon-b", "text": text})
        assert r.status_code == 200, r.text
    assert r.json()["ready"] is True
    assert {(r["session_id"], r["endpoint"]) for r in saved(client)} == {("anon-a", "intent"), ("anon-b", "chat")}
    assert [r["session_id"] for r in saved(client, endpoint="chat")] == ["anon-b"]
    assert [r["endpoint"] for r in saved(client, session_id="anon-a")] == ["intent"]
    assert saved(client, intent="passport_new") == []
    assert len(saved(client, limit=1)) == 1
    assert client.get("/v1/requests/completed", params={"endpoint": "sms"}).status_code == 422


def test_saving_survives_a_restart(client, real_mode, completed_db):
    nic_lost_in_badulla(real_mode, Chat(client))
    store = CompletedStore(completed_db)        # a new store on the same file, as after a restart
    assert [r["intent"] for r in store.list()] == ["nic_replace_lost"]


def test_off_saves_nothing(client, real_mode, monkeypatch, completed_db):
    monkeypatch.setenv("C1_COMPLETED_DB", "off")
    assert nic_lost_in_badulla(real_mode, Chat(client))["ready"] is True
    assert saved(client) == []
    assert not completed_db.exists()


def test_a_storage_error_does_not_fail_the_turn(client, real_mode, monkeypatch, caplog):
    class Broken:
        def record(self, *a):
            raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(completed, "get_store", lambda: Broken())
    with caplog.at_level(logging.WARNING, logger="c1-intent"):
        assert nic_lost_in_badulla(real_mode, Chat(client))["ready"] is True
    assert "completed request not saved" in caplog.text and "OperationalError" in caplog.text


def test_log_has_no_slot_values(client, real_mode, caplog):
    with caplog.at_level(logging.INFO, logger="c1-intent"):
        nic_lost_in_badulla(real_mode, Chat(client))
    assert "completed request saved" in caplog.text
    assert "Badulla" not in caplog.text


def test_stub_mode_lists_an_empty_store(client):
    assert pipeline.completed_requests() == []
    assert saved(client) == []


def test_completed_page_is_served_and_not_in_openapi(client):
    r = client.get("/demo/completed")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "/v1/requests/completed" in r.text
    assert "/demo/completed" not in client.get("/openapi.json").json()["paths"]
    assert "/demo/completed" in client.get("/demo").text
