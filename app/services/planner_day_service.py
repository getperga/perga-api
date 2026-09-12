import datetime as dt
import logging
from collections import defaultdict
from sqlalchemy.orm import Session

from app.const.planner import PlannerItemState
from app.core.db_utils import atomic_transaction, TransactionRollback
from app.models.planner import PlannerDayItem
from app.schemas.planner_day import PlannerDayItemCreateSchema, PlannerDayItemUpdateSchema
from app.services.base_service import BaseService

# Get logger for this module
logger = logging.getLogger(__name__)


class PlannerDayItemService(BaseService[PlannerDayItem]):
    model = PlannerDayItem

    @classmethod
    def get_new_item_index(cls, db: Session, day: dt.date, user_id: int) -> int:
        query = cls.get_base_query(db, user_id=user_id).filter(PlannerDayItem.day == day)
        max_index_item: PlannerDayItem | None = query.order_by(PlannerDayItem.index.desc()).first()
        return max_index_item.index + 1 if max_index_item else 0

    @classmethod
    def get_day_item(cls, db: Session, item_id: int, user_id: int) -> PlannerDayItem | None:
        query = cls.get_base_query(db, user_id=user_id).filter(PlannerDayItem.id == item_id)
        return query.first()

    @classmethod
    def get_items_by_day(cls, db: Session, day: dt.date, user_id: int) -> list[PlannerDayItem]:
        query = cls.get_base_query(db, user_id=user_id).filter(PlannerDayItem.day == day)
        return query.order_by(PlannerDayItem.index).all()

    @classmethod
    def get_items_by_range(
        cls, db: Session, start_date: dt.date, days_count: int, user_id: int
    ) -> dict[dt.date, list[PlannerDayItem]]:
        """ Get items for a range of days starting from start_date """
        end_date = start_date + dt.timedelta(days=days_count - 1)
        items = cls.get_base_query(db, user_id=user_id).filter(
            PlannerDayItem.day >= start_date,
            PlannerDayItem.day <= end_date
        ).order_by(PlannerDayItem.day, PlannerDayItem.index).all()

        result = defaultdict(list)
        for item in items:
            result[item.day].append(item)

        return result

    @classmethod
    def create_day_item(cls, db: Session, item: PlannerDayItemCreateSchema, user_id: int) -> PlannerDayItem:
        new_index = cls.get_new_item_index(db, item.day, user_id)

        db_item = PlannerDayItem(**item.model_dump(), index=new_index, user_id=user_id)
        db.add(db_item)
        db.commit()

        db.refresh(db_item)
        return db_item

    @classmethod
    def update_day_item(
        cls, db: Session, item_id: int, item: PlannerDayItemUpdateSchema, user_id: int
    ) -> PlannerDayItem | None:
        db_item = cls.get_day_item(db, item_id, user_id)
        if not db_item:
            return None

        update_data = item.model_dump(exclude_unset=True)
        for field, new_value in update_data.items():
            setattr(db_item, field, new_value)
        db.commit()

        db.refresh(db_item)
        return db_item

    @classmethod
    def delete_day_item(cls, db: Session, item_id: int, user_id: int) -> bool:
        db_item = cls.get_day_item(db, item_id, user_id)
        if not db_item:
            return False

        db_item.mark_as_deleted()
        db.commit()

        return True

    @classmethod
    def reorder_day_items(cls, db: Session, ordered_item_ids: list[int], user_id: int) -> bool:
        """ Update day items indexes accordingly to provided ordered list """
        new_index = 0

        try:
            with atomic_transaction(db):
                for item_id in ordered_item_ids:
                    db_item = cls.get_day_item(db, item_id, user_id)
                    if db_item:
                        db_item.index = new_index
                    new_index += 1
        except TransactionRollback as e:
            logger.warning(f'reorder_day_items: {str(e)}')
            return False

        return True

    @classmethod
    def copy_day_item(cls, db: Session, item_id: int, day: dt.date, user_id: int) -> PlannerDayItem | None:
        """ Create new item on specified date """
        db_item = cls.get_day_item(db, item_id, user_id)
        if not db_item:
            return None

        new_index = cls.get_new_item_index(db, day, user_id)
        new_db_item = PlannerDayItem(
            user_id=user_id,
            day=day,
            text=db_item.text,
            index=new_index
        )
        db.add(new_db_item)
        db.commit()

        return new_db_item

    @classmethod
    def snooze_day_item(cls, db: Session, item_id: int, day: dt.date, user_id: int) -> PlannerDayItem | None:
        """ Mark original item as snoozed and create new one on specified date """
        db_item = cls.get_day_item(db, item_id, user_id)
        if not db_item:
            return None

        try:
            with atomic_transaction(db):
                db_item.state = PlannerItemState.SNOOZED

                new_index = cls.get_new_item_index(db, day, user_id)
                new_db_item = PlannerDayItem(
                    user_id=user_id,
                    day=day,
                    text=db_item.text,
                    index=new_index,
                )
                db.add(new_db_item)
        except TransactionRollback as e:
            logger.warning(f'snooze_day_item: {str(e)}')
            return None

        return new_db_item
