"""Tests for app.schemas.routine."""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.common import TimeOfDay
from app.schemas.routine import RoutineCreate, RoutineItemCreate


def test_routine_item_create_valid() -> None:
    item = RoutineItemCreate(product_id=uuid4(), time_of_day=TimeOfDay.AM, step_order=1)
    assert item.time_of_day == "AM"


def test_routine_item_create_default_step_order() -> None:
    item = RoutineItemCreate(product_id=uuid4(), time_of_day=TimeOfDay.PM)
    assert item.step_order == 0


def test_routine_item_create_rejects_negative_step_order() -> None:
    with pytest.raises(ValidationError):
        RoutineItemCreate(product_id=uuid4(), time_of_day=TimeOfDay.AM, step_order=-1)


def test_routine_item_create_rejects_invalid_time_of_day() -> None:
    with pytest.raises(ValidationError):
        RoutineItemCreate(product_id=uuid4(), time_of_day="afternoon")


def test_routine_create_valid_with_items() -> None:
    routine = RoutineCreate(
        session_id=uuid4(),
        name="Evening Routine",
        items=[
            RoutineItemCreate(product_id=uuid4(), time_of_day=TimeOfDay.PM, step_order=0),
            RoutineItemCreate(product_id=uuid4(), time_of_day=TimeOfDay.PM, step_order=1),
        ],
    )
    assert len(routine.items) == 2


def test_routine_create_defaults_to_empty_items() -> None:
    routine = RoutineCreate(session_id=uuid4())
    assert routine.items == []
    assert routine.name == "My Routine"


def test_routine_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        RoutineCreate(session_id=uuid4(), name="")
