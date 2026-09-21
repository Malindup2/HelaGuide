def test_render_marks_disputed_fee(client, example):
    body = {"session_id": "anon-test", "plan": example("plan"), "trust": [example("trust")]}
    r = client.post("/v1/render", json=body)
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert steps[0]["fee_display"] == "Free"
    assert steps[1]["warning"] is not None
