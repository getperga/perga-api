from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.const.planner import PlannerAgendaType, PlannerAgendaAction
from app.services.auth_service import AuthService
from app.core.database import get_db
from app.schemas.planner_agenda import (
    PlannerAgendaSchema, PlannerAgendaCreateSchema, PlannerAgendaUpdateSchema,
    PlannerAgendaItemSchema, PlannerAgendaItemCreateSchema, PlannerAgendaItemUpdateSchema,
    ReorderAgendaItemsSchema, ReorderAgendasSchema,
    CopyAgendaItemSchema, MoveAgendaItemSchema,
    PlannerAgendaActionSchema,
)
from app.services.planner_agenda_service import PlannerAgendaService
from app.services.planner_agenda_item_service import PlannerAgendaItemService
from app.schemas.user import UserSchema

router = APIRouter()


@router.get("/", response_model=list[PlannerAgendaSchema])
def get_agendas(
    agenda_types: list[PlannerAgendaType] | None = Query(
        None, description="Agenda types to include: monthly, custom, archived"
    ),
    selected_day: date | None = Query(
        None, description="Reference day to resolve monthly agenda (defaults to today)"
    ),
    with_counts: bool | None = Query(False, description="Include agenda items counts"),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    agendas = PlannerAgendaService.get_agendas(db, current_user.id, agenda_types, selected_day, with_counts)
    return agendas


@router.post("/", response_model=PlannerAgendaSchema)
def create_agenda(
    agenda_item: PlannerAgendaCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    db_agenda = PlannerAgendaService.create_planner_agenda(db=db, agenda_item=agenda_item, user_id=current_user.id)
    return db_agenda


@router.put("/{agenda_id}/", response_model=PlannerAgendaSchema)
def update_agenda(
    agenda_id: int,
    agenda_item: PlannerAgendaUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # validate agenda_type for archive/unarchive actions
    if agenda_item.agenda_type and agenda_item.agenda_type not in [
        PlannerAgendaType.ARCHIVED, PlannerAgendaType.CUSTOM
    ]:
        raise HTTPException(status_code=400, detail="Bad request")

    # Check if the agenda belongs to the current user
    db_agenda = PlannerAgendaService.get_planner_agenda(db, agenda_id=agenda_id, user_id=current_user.id)
    if not db_agenda:
        raise HTTPException(status_code=404, detail="Planner agenda not found")

    # Then update it
    db_agenda = PlannerAgendaService.update_planner_agenda(
        db, agenda_id=agenda_id, agenda_item=agenda_item, user_id=current_user.id
    )
    return db_agenda


@router.delete("/{agenda_id}/", response_model=dict)
def delete_agenda(
    agenda_id: int,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # First check if the agenda belongs to the current user
    db_agenda = PlannerAgendaService.get_planner_agenda(db, agenda_id=agenda_id, user_id=current_user.id)
    if not db_agenda:
        raise HTTPException(status_code=404, detail="Planner agenda not found")

    # Then delete it
    success = PlannerAgendaService.delete_planner_agenda(db, agenda_id=agenda_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete planner agenda")
    return {"detail": "Planner agenda and its items deleted successfully"}


@router.post("/reorder/", response_model=dict)
def reorder_agendas(
    request: ReorderAgendasSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # First verify all agendas belong to the current user
    for agenda_id in request.ordered_agenda_ids:
        db_agenda = PlannerAgendaService.get_planner_agenda(db, agenda_id=agenda_id, user_id=current_user.id)
        if not db_agenda:
            raise HTTPException(status_code=404, detail=f"Planner agenda with id {agenda_id} not found")

    # Then reorder them
    success = PlannerAgendaService.reorder_agendas(db, request.ordered_agenda_ids, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to reorder agendas")
    return {"detail": "Agendas reordered successfully"}


# Item routes
@router.post("/items/", response_model=PlannerAgendaItemSchema)
def create_agenda_item(
    item: PlannerAgendaItemCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # Check if agenda exists and belongs to the current user
    db_agenda = PlannerAgendaService.get_planner_agenda(db, item.agenda_id, user_id=current_user.id)
    if not db_agenda:
        raise HTTPException(status_code=404, detail="Planner agenda not found")

    return PlannerAgendaItemService.create_agenda_item(db=db, item=item, user_id=current_user.id)


@router.put("/items/{item_id}/", response_model=PlannerAgendaItemSchema)
def update_agenda_item(
    item_id: int,
    item: PlannerAgendaItemUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # First check if the item exists and belongs to the current user
    db_item = PlannerAgendaItemService.get_agenda_item(db, item_id=item_id, user_id=current_user.id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Planner agenda item not found")

    # If agenda is being updated, check if it exists and belongs to the current user
    if item.agenda_id is not None:
        db_agenda = PlannerAgendaService.get_planner_agenda(db, item.agenda_id, user_id=current_user.id)
        if not db_agenda:
            raise HTTPException(status_code=404, detail="Target planner agenda not found")

    # Then update the item
    db_item = PlannerAgendaItemService.update_agenda_item(db, item_id=item_id, item=item, user_id=current_user.id)
    return db_item


@router.delete("/items/{item_id}/", response_model=dict)
def delete_agenda_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # First check if the item exists and belongs to the current user
    db_item = PlannerAgendaItemService.get_agenda_item(db, item_id=item_id, user_id=current_user.id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Planner agenda item not found")

    # Then delete it
    success = PlannerAgendaItemService.delete_agenda_item(db, item_id=item_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete planner agenda item")
    return {"detail": "Planner agenda item deleted successfully"}


@router.post("/items/reorder/", response_model=dict)
def reorder_agenda_items(
    request: ReorderAgendaItemsSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # First verify all items belong to the current user
    for item_id in request.ordered_item_ids:
        db_item = PlannerAgendaItemService.get_agenda_item(db, item_id=item_id, user_id=current_user.id)
        if not db_item:
            raise HTTPException(status_code=404, detail=f"Planner agenda item with id {item_id} not found")

    # Then reorder them
    success = PlannerAgendaItemService.reorder_agenda_items(db, request.ordered_item_ids, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to reorder agenda items")
    return {"detail": "Agenda items reordered successfully"}


@router.get("/items/", response_model=dict[int, list[PlannerAgendaItemSchema]])
def get_items_by_agendas(
    agenda_ids: list[int] = Query(..., description="List of agenda IDs"),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    user_agenda_ids = PlannerAgendaService.get_user_agenda_ids(db, agenda_ids, current_user.id)
    agenda_items_map = PlannerAgendaItemService.get_items_grouped_by_agenda_id(db, user_agenda_ids, current_user.id)
    return agenda_items_map


@router.post("/items/{item_id}/copy/", response_model=PlannerAgendaItemSchema)
def copy_agenda_item(
    request: CopyAgendaItemSchema,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # Check that the item exists and belongs to the current user
    db_item = PlannerAgendaItemService.get_agenda_item(db, item_id=item_id, user_id=current_user.id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Planner agenda item not found")

    # Check that target agenda exists and belongs to the current user
    db_agenda = PlannerAgendaService.get_planner_agenda(db, request.agenda_id, user_id=current_user.id)
    if not db_agenda:
        raise HTTPException(status_code=404, detail="Target planner agenda not found")

    new_db_item = PlannerAgendaItemService.copy_agenda_item(
        db, item_id=item_id, agenda_id=request.agenda_id, user_id=current_user.id
    )
    if not new_db_item:
        raise HTTPException(status_code=400, detail="Failed to copy planner agenda item")
    return new_db_item


@router.post("/items/{item_id}/move/", response_model=PlannerAgendaItemSchema)
def move_agenda_item(
    request: MoveAgendaItemSchema,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    # Check that the item exists and belongs to the current user
    db_item = PlannerAgendaItemService.get_agenda_item(db, item_id=item_id, user_id=current_user.id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Planner agenda item not found")

    # Check that target agenda exists and belongs to the current user
    db_agenda = PlannerAgendaService.get_planner_agenda(db, request.agenda_id, user_id=current_user.id)
    if not db_agenda:
        raise HTTPException(status_code=404, detail="Target planner agenda not found")

    new_db_item = PlannerAgendaItemService.move_agenda_item(
        db, item_id=item_id, agenda_id=request.agenda_id, user_id=current_user.id
    )
    if not new_db_item:
        raise HTTPException(status_code=400, detail="Failed to snooze planner agenda item")
    return new_db_item


@router.post("/{agenda_id}/action/", response_model=dict)
def agenda_action(
    agenda_id: int,
    request: PlannerAgendaActionSchema,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(AuthService.get_current_user)
):
    """ Unified agenda-level action endpoint. Supported actions: delete_finished_items, sort_items_by_state. """
    # Verify agenda belongs to current user
    db_agenda = PlannerAgendaService.get_planner_agenda(db, agenda_id=agenda_id, user_id=current_user.id)
    if not db_agenda:
        raise HTTPException(status_code=404, detail="Planner agenda not found")

    if request.action == PlannerAgendaAction.DELETE_FINISHED_ITEMS:
        PlannerAgendaItemService.delete_finished_agenda_items(db, agenda_id=agenda_id, user_id=current_user.id)
    elif request.action == PlannerAgendaAction.SORT_ITEMS_BY_STATE:
        success = PlannerAgendaItemService.sort_agenda_items_by_state(
            db, agenda_id=agenda_id, user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to sort items")
    else:
        raise HTTPException(status_code=400, detail="Unsupported action")

    return {"detail": "Action is applied successfully"}
