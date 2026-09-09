import pytest

from camreview.detection.categories import category_for


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("person", "person"),
        ("dog", "pet"),
        ("cat", "pet"),
        ("car", "vehicle"),
        ("truck", "vehicle"),
        ("bear", "animal"),
        ("backpack", "other"),
    ],
)
def test_category_mapping(raw: str, expected: str) -> None:
    assert category_for(raw) == expected
