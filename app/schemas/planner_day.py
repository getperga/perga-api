from datetime import date
from pydantic import BaseModel

from app.const.planner import PlannerItemState


# Base schemas for planner items
class BasePlannerItemBaseSchema(BaseModel):
    text: str
    index: int
    state: PlannerItemState


class PlannerDayItemCreateSchema(BaseModel):
    day: date
    text: str


class PlannerDayItemUpdateSchema(BaseModel):
    day: date | None = None
    text: str | None = None
    state: PlannerItemState | None = None


class PlannerDayItemSchema(BaseModel):
    id: int
    day: date
    text: str
    state: PlannerItemState


class ReorderDayItemsSchema(BaseModel):
    ordered_item_ids: list[int]


class CopyDayItemSchema(BaseModel):
    day: date


class SnoozeDayItemSchema(BaseModel):
    day: date
