import pytest

from superteacher.metrics import letter_and_gpa


@pytest.mark.parametrize("pct,letter,gpa", [(100, "A", 4.0), (93, "A", 4.0), (92.9, "A-", 3.7), (80, "B-", 2.7), (59, "F", 0.0)])
def test_letter_bands(pct, letter, gpa):
    assert letter_and_gpa(pct) == (letter, gpa)


def test_no_data_gives_none():
    assert letter_and_gpa(None) == (None, None)
