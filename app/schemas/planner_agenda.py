from pydantic import BaseModel

from app.const.planner import PlannerAgendaType, PlannerItemState, PlannerAgendaAction
from app.schemas.planner_day import BasePlannerItemBaseSchema


class PlannerAgendaCreateSchema(BaseModel):
    agenda_type: PlannerAgendaType
    name: str
    index: int | None = None


class PlannerAgendaUpdateSchema(BaseModel):
    name: str | None = None
    index: int | None = None
    agenda_type: PlannerAgendaType | None = None


class PlannerAgendaSchema(BaseModel):
    id: int
    agenda_type: str
    name: str
    index: int
    todo_items_cnt: int = 0
    completed_items_cnt: int = 0

    class Config:
        from_attributes = True


# Agenda Item schemas
class PlannerAgendaItemCreateSchema(BaseModel):
    agenda_id: int
    text: str


class PlannerAgendaItemUpdateSchema(BaseModel):
    agenda_id: int | None = None
    text: str | None = None
    state: PlannerItemState | None = None


class PlannerAgendaItemSchema(BasePlannerItemBaseSchema):
    id: int
    agenda_id: int


class PlannerAgendasWithItemsSchema(BaseModel):
    agendas: list[PlannerAgendaSchema]
    items: dict[int, list[PlannerAgendaItemSchema]]


class ReorderAgendaItemsSchema(BaseModel):
    ordered_item_ids: list[int]


class ReorderAgendasSchema(BaseModel):
    ordered_agenda_ids: list[int]


class CopyAgendaItemSchema(BaseModel):
    agenda_id: int


class MoveAgendaItemSchema(BaseModel):
    agenda_id: int


class PlannerAgendaActionSchema(BaseModel):
    action: PlannerAgendaAction
