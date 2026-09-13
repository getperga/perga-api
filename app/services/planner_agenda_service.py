import datetime as dt
import logging
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.const.planner import (
    PlannerAgendaType, PlannerItemState, PLANNER_CUSTOM_AGENDA_INDEX_MIN, PLANNER_MONTHLY_AGENDA_INDEX,
)
from app.core.db_utils import atomic_transaction, TransactionRollback
from app.models.planner import PlannerAgenda, PlannerAgendaItem
from app.schemas.planner_agenda import PlannerAgendaCreateSchema, PlannerAgendaUpdateSchema
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


class PlannerAgendaService(BaseService[PlannerAgenda]):
    model = PlannerAgenda

    @classmethod
    def get_agendas(
        cls, db: Session, user_id: int, agenda_types: list[PlannerAgendaType], selected_day: dt.date | None = None,
        with_counts: bool = False
    ) -> list[PlannerAgenda]:
        """
        Returns list of user agendas depending on provided agenda types:
        1. Monthly - selected and next month agendas
        2. Custom - active custom agendas
        3. Archived - archived custom agendas
        """
        base_query = cls.get_base_query(db, user_id=user_id)
        result_agendas = []

        if PlannerAgendaType.MONTHLY in agenda_types:
            if not selected_day:
                selected_day = dt.datetime.today()

            selected_month_name = selected_day.strftime('%B %Y')
            next_month_name = (selected_day.replace(day=1) + relativedelta(months=1)).strftime('%B %Y')
            month_names = [selected_month_name, next_month_name]
            month_agendas = base_query.filter(
                PlannerAgenda.agenda_type == PlannerAgendaType.MONTHLY.value,
                PlannerAgenda.name.in_(month_names)
            ).all()

            # Ensure that month agenda exists
            for month_name in month_names:
                try:
                    month_agenda = [agenda for agenda in month_agendas if agenda.name == month_name][0]
                except IndexError:
                    agenda_create = PlannerAgendaCreateSchema(
                        name=month_name,
                        agenda_type=PlannerAgendaType.MONTHLY,
                        index=PLANNER_MONTHLY_AGENDA_INDEX
                    )
                    month_agenda = cls.create_planner_agenda(db, agenda_create, user_id)
                result_agendas.append(month_agenda)

        if PlannerAgendaType.CUSTOM in agenda_types:
            custom_agendas = base_query.filter(
                PlannerAgenda.agenda_type == PlannerAgendaType.CUSTOM
            ).order_by(PlannerAgenda.index).all()
            result_agendas.extend(custom_agendas)

        if PlannerAgendaType.ARCHIVED in agenda_types:
            archived_agendas = base_query.filter(PlannerAgenda.agenda_type == PlannerAgendaType.ARCHIVED).all()
            result_agendas.extend(archived_agendas)

        # Add items counts to each agenda
        if result_agendas and with_counts:
            cls._calc_items_counts(db, result_agendas)

        return result_agendas

    @classmethod
    def _calc_items_counts(cls, db: Session, agendas: list[PlannerAgenda]) -> None:
        if not agendas:
            return

        agenda_ids = [agenda.id for agenda in agendas]

        items_cnt_query = db.query(
            PlannerAgendaItem.agenda_id,
            func.sum(
                case((PlannerAgendaItem.state == PlannerItemState.TODO, 1), else_=0)
            ).label('todo_cnt'),
            func.sum(
                case((PlannerAgendaItem.state == PlannerItemState.COMPLETED, 1), else_=0)
            ).label('completed_cnt'),
        ).filter(
            PlannerAgendaItem.agenda_id.in_(agenda_ids),
            PlannerAgendaItem.is_deleted.is_(False)
        ).group_by(PlannerAgendaItem.agenda_id).all()

        items_cnt_map = {
            row.agenda_id: (int(row.todo_cnt or 0), int(row.completed_cnt or 0)) for row in items_cnt_query
        }
        for agenda in agendas:
            todo_items_cnt, completed_items_cnt = items_cnt_map.get(agenda.id, (0, 0))
            setattr(agenda, 'todo_items_cnt', todo_items_cnt)
            setattr(agenda, 'completed_items_cnt', completed_items_cnt)

    @classmethod
    def get_new_agenda_index(cls, db: Session, user_id) -> int:
        query = cls.get_base_query(db, user_id=user_id)
        max_index_agenda = query.order_by(PlannerAgenda.index.desc()).first()
        return max_index_agenda.index + 1 if max_index_agenda else PLANNER_CUSTOM_AGENDA_INDEX_MIN

    @classmethod
    def get_planner_agenda(cls, db: Session, agenda_id: int, user_id: int) -> PlannerAgenda | None:
        query = cls.get_base_query(db, user_id=user_id).filter(PlannerAgenda.id == agenda_id)
        return query.first()

    @classmethod
    def create_planner_agenda(cls, db: Session, agenda_item: PlannerAgendaCreateSchema, user_id: int) -> PlannerAgenda:
        if agenda_item.index is None:
            agenda_item.index = cls.get_new_agenda_index(db, user_id)

        db_agenda = PlannerAgenda(**agenda_item.model_dump(), user_id=user_id)
        db.add(db_agenda)
        db.commit()

        db.refresh(db_agenda)
        return db_agenda

    @classmethod
    def update_planner_agenda(
        cls, db: Session, agenda_id: int, agenda_item: PlannerAgendaUpdateSchema, user_id: int
    ) -> PlannerAgenda | None:
        db_agenda = cls.get_planner_agenda(db, agenda_id, user_id)
        if not db_agenda:
            return None

        update_data = agenda_item.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_agenda, field, value)
        db.commit()

        db.refresh(db_agenda)
        cls._calc_items_counts(db, [db_agenda])
        return db_agenda

    @classmethod
    def delete_planner_agenda(cls, db: Session, agenda_id: int, user_id: int) -> bool:
        db_agenda = cls.get_planner_agenda(db, agenda_id, user_id)
        if not db_agenda:
            return False

        # Mark as deleted all items in this agenda as well
        try:
            with atomic_transaction(db):
                db.query(PlannerAgendaItem).filter(
                    PlannerAgendaItem.is_deleted.is_(False),
                    PlannerAgendaItem.agenda_id == agenda_id
                ).update({
                    'is_deleted': True,
                    'deleted_dt': dt.datetime.now(dt.timezone.utc),
                })
                db_agenda.mark_as_deleted()
        except TransactionRollback as e:
            logger.warning(f'delete_planner_agenda: {str(e)}')
            return False

        return True

    @classmethod
    def reorder_agendas(cls, db: Session, ordered_agenda_ids: list[int], user_id: int) -> bool:
        new_index = PLANNER_CUSTOM_AGENDA_INDEX_MIN

        try:
            with atomic_transaction(db):
                for agenda_id in ordered_agenda_ids:
                    db_agenda = cls.get_planner_agenda(db, agenda_id, user_id)
                    if db_agenda:
                        db_agenda.index = new_index
                    new_index += 1
        except TransactionRollback as e:
            logger.warning(f'reorder_agendas: {str(e)}')
            return False

        return True
