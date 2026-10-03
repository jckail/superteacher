"""CSV header detection must not discard valid headerless students."""

import pytest

from tests.test_api import mk_class


def imported_roster(client, csv_text):
    _, section = mk_class(client)
    response = client.post(f"/api/sections/{section['id']}/import", json={"csv": csv_text})
    assert response.status_code == 200
    roster = client.get("/api/students", params={"section_id": section["id"]}).json()
    return response.json(), {student["name"]: student["grade_level"] for student in roster}


@pytest.mark.parametrize("name", ["Name", "Student", "Student Name"])
def test_headerless_first_student_with_header_like_name_is_imported(client, name):
    result, roster = imported_roster(client, f"{name},9\nAda,10")
    assert result == {"created": 2, "skipped": []}
    assert roster == {name: 9, "Ada": 10}


@pytest.mark.parametrize("name", ["Name", "Student", "Student Name"])
def test_headerless_single_column_header_like_name_uses_default_grade(client, name):
    result, roster = imported_roster(client, name)
    assert result == {"created": 1, "skipped": []}
    assert roster == {name: 9}


@pytest.mark.parametrize("name_header", ["name", "student", "student name"])
@pytest.mark.parametrize("grade_header", ["grade_level", "grade level", "grade"])
def test_recognized_header_pairs_are_discarded(client, name_header, grade_header):
    result, roster = imported_roster(client, f"{name_header},{grade_header}\nAda,10")
    assert result == {"created": 1, "skipped": []}
    assert roster == {"Ada": 10}


def test_bom_whitespace_case_and_quoted_names_keep_csv_semantics(client):
    result, roster = imported_roster(client, '\ufeff  STUDENT   NAME ,  GRADE   LEVEL \n"Hopper, Grace",11\n')
    assert result == {"created": 1, "skipped": []}
    assert roster == {"Hopper, Grace": 11}


def test_unrecognized_header_like_first_row_is_reported_invalid(client):
    result, roster = imported_roster(client, "Name,not-a-grade\nAda,10")
    assert result == {"created": 1, "skipped": ["Row 1: invalid name or grade level"]}
    assert roster == {"Ada": 10}
