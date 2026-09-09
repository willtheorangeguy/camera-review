from __future__ import annotations

PERSON = {"person"}
PETS = {"dog", "cat"}
VEHICLES = {"car", "truck", "bus", "motorcycle", "bicycle"}
ANIMALS = {"bird", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}


def category_for(class_name: str) -> str:
    normalized = class_name.casefold()
    if normalized in PERSON:
        return "person"
    if normalized in PETS:
        return "pet"
    if normalized in VEHICLES:
        return "vehicle"
    if normalized in ANIMALS:
        return "animal"
    return "other"
