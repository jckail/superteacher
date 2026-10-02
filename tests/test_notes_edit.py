"""Notes can be edited and removed only through their owning student."""

from datetime import datetime

import pytest

from tests.test_api import mk_class, mk_student


def test_note_edit_and_delete_preserves_identity_and_creation_time(client):
    _, section = mk_class(client)
    student = mk_student(client, section)
    note = client.post(f"/api/students/{student['id']}/notes", json={"body": "Original"}).json()
    created_at = datetime.fromisoformat(note["created_at"]).replace(tzinfo=None)
    note = client.get(f"/api/students/{student['id']}").json()["notes"][0]
    url = f"/api/students/{student['id']}/notes/{note['id']}"
    edited = client.patch(url, json={"body": "  Parent follow-up completed  "})
    assert edited.status_code == 200
    assert edited.json() == {**note, "body": "Parent follow-up completed"}
    assert datetime.fromisoformat(edited.json()["created_at"]).replace(tzinfo=None) == created_at
    assert client.get(f"/api/students/{student['id']}").json()["notes"] == [edited.json()]
    deleted = client.delete(url)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f"/api/students/{student['id']}").json()["notes"] == []
    assert client.patch(url, json={"body": "Again"}).status_code == 404
    assert client.delete(url).status_code == 404


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_note_mutations_are_scoped_to_student(client, method):
    _, section = mk_class(client)
    owner = mk_student(client, section, "Owner")
    other = mk_student(client, section, "Other")
    note = client.post(f"/api/students/{owner['id']}/notes", json={"body": "Private"}).json()
    original = client.get(f"/api/students/{owner['id']}").json()["notes"]
    kwargs = {"json": {"body": "Changed"}} if method == "patch" else {}
    for student_id, note_id in [(other["id"], note["id"]), ("missing", note["id"]), (owner["id"], "missing")]:
        response = getattr(client, method)(f"/api/students/{student_id}/notes/{note_id}", **kwargs)
        assert response.status_code == 404
    assert client.get(f"/api/students/{owner['id']}").json()["notes"] == original


@pytest.mark.parametrize("body", [{}, {"body": None}, {"body": ""}, {"body": "  "}, {"body": "x" * 2001}])
def test_invalid_note_edits_leave_note_unchanged(client, body):
    _, section = mk_class(client)
    student = mk_student(client, section)
    note = client.post(f"/api/students/{student['id']}/notes", json={"body": "Original"}).json()
    original = client.get(f"/api/students/{student['id']}").json()["notes"]
    assert client.patch(f"/api/students/{student['id']}/notes/{note['id']}", json=body).status_code == 422
    assert client.get(f"/api/students/{student['id']}").json()["notes"] == original
