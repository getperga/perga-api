import pytest
from sqlalchemy.orm import Session

from app.const.planner import PlannerItemState, PlannerAgendaType
from app.models.planner import PlannerAgenda, PlannerAgendaItem
from app.schemas.planner_agenda import PlannerAgendaItemCreateSchema, PlannerAgendaItemUpdateSchema
from app.services.planner_agenda_item_service import PlannerAgendaItemService


class TestPlannerAgendaItemService:
    @pytest.fixture
    def test_agenda(self, test_db: Session, test_user):
        agenda = PlannerAgenda(
            name='Test Agenda',
            index=0,
            agenda_type=PlannerAgendaType.CUSTOM,
            user_id=test_user.id
        )
        test_db.add(agenda)
        test_db.commit()
        test_db.refresh(agenda)
        return agenda

    def test_get_new_agenda_item_index(self, test_db: Session, test_user, test_agenda):
        # When there are no items, so new index should be 0
        index = PlannerAgendaItemService.get_new_agenda_item_index(
            test_db,
            test_agenda.id,
            test_user.id
        )
        assert index == 0

        # Create an item with index 0
        item = PlannerAgendaItem(
            text='Test Item',
            index=0,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        test_db.add(item)
        test_db.commit()

        # Now new index should be 1
        index = PlannerAgendaItemService.get_new_agenda_item_index(
            test_db,
            test_agenda.id,
            test_user.id
        )
        assert index == 1

    def test_get_agenda_item(self, test_db: Session, test_user, test_agenda):
        # Create an item
        item = PlannerAgendaItem(
            text='Test Item',
            index=0,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)

        # Get the item
        db_item = PlannerAgendaItemService.get_agenda_item(test_db, item.id, test_user.id)
        assert db_item is not None
        assert db_item.id == item.id
        assert db_item.text == item.text
        assert db_item.state == PlannerItemState.TODO

        # Try to get a non-existent item
        db_item = PlannerAgendaItemService.get_agenda_item(test_db, 777, test_user.id)
        assert db_item is None

        # Try to get an item with a different user_id
        db_item = PlannerAgendaItemService.get_agenda_item(test_db, item.id, 7)
        assert db_item is None

    def test_create_agenda_item(self, test_db: Session, test_user, test_agenda):
        # Create an item
        item_create = PlannerAgendaItemCreateSchema(
            text='Test Item',
            agenda_id=test_agenda.id
        )
        db_item = PlannerAgendaItemService.create_agenda_item(test_db, item_create, test_user.id)
        
        # Check that the item was created correctly
        assert db_item.id is not None
        assert db_item.text == item_create.text
        assert db_item.state == PlannerItemState.TODO
        assert db_item.index == 0
        assert db_item.user_id == test_user.id
        assert db_item.agenda_id == test_agenda.id

    def test_update_agenda_item(self, test_db: Session, test_user, test_agenda):
        # Create an item
        item = PlannerAgendaItem(
            text='Test Item',
            index=0,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)
        
        # Update the item
        item_update = PlannerAgendaItemUpdateSchema(
            text='Updated Item',
            state=PlannerItemState.COMPLETED
        )
        db_item = PlannerAgendaItemService.update_agenda_item(test_db, item.id, item_update, test_user.id)
        
        # Check that the item was updated correctly
        assert db_item.id == item.id
        assert db_item.text == item_update.text
        assert db_item.state == PlannerItemState.COMPLETED
        assert db_item.index == 0
        
        # Try to update a non-existent item
        db_item = PlannerAgendaItemService.update_agenda_item(test_db, 444, item_update, test_user.id)
        assert db_item is None
        
        # Try to update an item with a different user_id
        db_item = PlannerAgendaItemService.update_agenda_item(test_db, item.id, item_update, 7)
        assert db_item is None

    def test_delete_agenda_item(self, test_db: Session, test_user, test_agenda):
        # Create an item
        item = PlannerAgendaItem(
            text='Test Item',
            index=0,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)
        
        # Delete the item
        delete_result = PlannerAgendaItemService.delete_agenda_item(test_db, item.id, test_user.id)
        assert delete_result is True
        
        # Check that the item was marked as deleted
        db_item = test_db.query(PlannerAgendaItem).filter(PlannerAgendaItem.id == item.id).first()
        assert db_item.is_deleted is True
        assert db_item.deleted_dt is not None
        
        # Try to delete a non-existent item
        delete_result = PlannerAgendaItemService.delete_agenda_item(test_db, 666, test_user.id)
        assert delete_result is False
        
        # Try to delete an item with a different user_id
        delete_result = PlannerAgendaItemService.delete_agenda_item(test_db, item.id, 7)
        assert delete_result is False

    def test_reorder_agenda_items(self, test_db: Session, test_user, test_agenda):
        # Create some items
        item1 = PlannerAgendaItem(
            text='Item 1',
            index=0,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        item2 = PlannerAgendaItem(
            text='Item 2',
            index=1,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        item3 = PlannerAgendaItem(
            text='Item 3',
            index=2,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        test_db.add_all([item1, item2, item3])
        test_db.commit()
        test_db.refresh(item1)
        test_db.refresh(item2)
        test_db.refresh(item3)
        
        # Reorder the items (3, 1, 2)
        reorder_result = PlannerAgendaItemService.reorder_agenda_items(
            test_db,
            [item3.id, item1.id, item2.id],
            test_user.id
        )
        assert reorder_result is True
        
        # Check that the items were reordered correctly
        db_item1 = test_db.query(PlannerAgendaItem).filter(PlannerAgendaItem.id == item1.id).first()
        db_item2 = test_db.query(PlannerAgendaItem).filter(PlannerAgendaItem.id == item2.id).first()
        db_item3 = test_db.query(PlannerAgendaItem).filter(PlannerAgendaItem.id == item3.id).first()
        assert db_item3.index == 0
        assert db_item1.index == 1
        assert db_item2.index == 2

    def test_delete_finished_agenda_items(self, test_db: Session, test_user, test_agenda):
        items = [
            PlannerAgendaItem(
                text='t1',
                index=0,
                state=PlannerItemState.TODO,
                user_id=test_user.id,
                agenda_id=test_agenda.id
            ),
            PlannerAgendaItem(
                text='t2',
                index=1,
                state=PlannerItemState.COMPLETED,
                user_id=test_user.id,
                agenda_id=test_agenda.id
            ),
            PlannerAgendaItem(
                text='t3',
                index=2,
                state=PlannerItemState.SNOOZED,
                user_id=test_user.id,
                agenda_id=test_agenda.id
            ),
            PlannerAgendaItem(
                text='t4',
                index=3,
                state=PlannerItemState.DROPPED,
                user_id=test_user.id,
                agenda_id=test_agenda.id
            ),
        ]
        test_db.add_all(items)
        test_db.commit()

        delete_result = PlannerAgendaItemService.delete_finished_agenda_items(test_db, test_agenda.id, test_user.id)
        assert delete_result is True

        refreshed = test_db.query(PlannerAgendaItem).filter(
            PlannerAgendaItem.agenda_id == test_agenda.id
        ).order_by(PlannerAgendaItem.index).all()
        assert refreshed[0].is_deleted is False
        assert refreshed[1].is_deleted is True and refreshed[1].deleted_dt is not None
        assert refreshed[2].is_deleted is True and refreshed[2].deleted_dt is not None
        assert refreshed[3].is_deleted is True and refreshed[3].deleted_dt is not None

    def test_sort_agenda_items_by_state(self, test_db: Session, test_user, test_agenda):
        # Original order by index: A(todo), B(completed), C(todo), D(snoozed), E(completed), F(dropped)
        a = PlannerAgendaItem(
            text='A',
            index=0,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        b = PlannerAgendaItem(
            text='B',
            index=1,
            state=PlannerItemState.COMPLETED,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        c = PlannerAgendaItem(
            text='C',
            index=2,
            state=PlannerItemState.TODO,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        d = PlannerAgendaItem(
            text='D',
            index=3,
            state=PlannerItemState.SNOOZED,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        e = PlannerAgendaItem(
            text='E',
            index=4,
            state=PlannerItemState.COMPLETED,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        f = PlannerAgendaItem(
            text='F',
            index=5,
            state=PlannerItemState.DROPPED,
            user_id=test_user.id,
            agenda_id=test_agenda.id
        )
        test_db.add_all([a, b, c, d, e, f])
        test_db.commit()

        sort_result = PlannerAgendaItemService.sort_agenda_items_by_state(test_db, test_agenda.id, test_user.id)
        assert sort_result is True

        # Fetch by new index order
        ordered_items = test_db.query(PlannerAgendaItem).filter(
            PlannerAgendaItem.agenda_id == test_agenda.id
        ).order_by(PlannerAgendaItem.index).all()

        # Expect completed first (B, E), then snoozed (D), then dropped (F), then todo (A, C)
        texts_by_index = [ordered_item.text for ordered_item in ordered_items]
        assert texts_by_index == ['B', 'E', 'D', 'F', 'A', 'C']
        assert ordered_items[0].text == 'B' and ordered_items[1].text == 'E'
