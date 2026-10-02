from superteacher.models import OWNER_ID


def test_chat_without_key_streams_notice_then_done(client):
    with client.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "Who needs help?"})
        first = ws.receive_json()
        assert first["type"] == "delta" and "ANTHROPIC_API_KEY" in first["text"]
        assert ws.receive_json()["type"] == "done"
        ws.send_json({"content": "again"})  # connection stays usable
        assert ws.receive_json()["type"] == "delta"


def test_context_contains_real_roster(seeded):
    from superteacher import ai

    with seeded.app.state.session_factory() as db:
        ctx = ai.build_context(db, OWNER_ID)
    assert "Roster snapshot (45 students)" in ctx and "Algebra I" in ctx
