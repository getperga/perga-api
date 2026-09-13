from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.const.planner import PlannerAgendaType, PlannerItemState
from app.core.config import settings
from app.models.planner import PlannerAgenda, PlannerAgendaItem


class TestPlannerAgendaAPI:
    def test_get_agendas_with_items(self, client: TestClient, test_db: Session, test_user, auth_headers):
        agendas = [
            PlannerAgenda(
                name='Agenda with item',
                agenda_type=PlannerAgendaType.CUSTOM,
                user_id=test_user.id,
                index=1,
            ),
            PlannerAgenda(
                name='Empty agenda',
                agenda_type=PlannerAgendaType.CUSTOM,
                user_id=test_user.id,
                index=2,
            ),
        ]
        test_db.add_all(agendas)
        test_db.commit()
        for agenda in agendas:
            test_db.refresh(agenda)

        item = PlannerAgendaItem(
            text='Included item',
            state=PlannerItemState.TODO,
            agenda_id=agendas[0].id,
            user_id=test_user.id,
            index=0,
        )
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)

        response = client.get(
            f'{settings.API_V1_STR}/planner/agendas/',
            params={'agenda_types': 'custom', 'with_items': 'true'},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert [agenda['id'] for agenda in data['agendas']] == [agenda.id for agenda in agendas]
        assert [entry['id'] for entry in data['items'][str(agendas[0].id)]] == [item.id]
        assert data['items'][str(agendas[1].id)] == []

    def test_get_agendas_without_items(
        self, client: TestClient, test_db: Session, test_user, auth_headers
    ):
        agenda = PlannerAgenda(
            name='Settings agenda',
            agenda_type=PlannerAgendaType.CUSTOM,
            user_id=test_user.id,
            index=1,
        )
        test_db.add(agenda)
        test_db.commit()
        test_db.refresh(agenda)

        response = client.get(
            f'{settings.API_V1_STR}/planner/agendas/',
            params={'agenda_types': 'custom'},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert [entry['id'] for entry in response.json()] == [agenda.id]

    def test_update_agenda_returns_counts(self, client: TestClient, test_db: Session, test_user, auth_headers):
        # Create an agenda
        agenda = PlannerAgenda(
            name='API Test Agenda',
            agenda_type=PlannerAgendaType.CUSTOM,
            user_id=test_user.id,
            index=1
        )
        test_db.add(agenda)
        test_db.commit()
        test_db.refresh(agenda)

        # Add items to db
        item1 = PlannerAgendaItem(
            text='Item 1',
            state=PlannerItemState.TODO,
            agenda_id=agenda.id,
            user_id=test_user.id
        )
        item2 = PlannerAgendaItem(
            text='Item 2',
            state=PlannerItemState.COMPLETED,
            agenda_id=agenda.id,
            user_id=test_user.id
        )
        test_db.add_all([item1, item2])
        test_db.commit()

        # Update the agenda via API
        response = client.put(
            f'{settings.API_V1_STR}/planner/agendas/{agenda.id}/',
            json={'name': 'Updated API Agenda'},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data['name'] == 'Updated API Agenda'
        assert data['todo_items_cnt'] == 1
        assert data['completed_items_cnt'] == 1

    def test_create_agenda_returns_zero_counts(self, client: TestClient, test_db: Session, test_user, auth_headers):
        # Create an agenda via API
        response = client.post(
            f'{settings.API_V1_STR}/planner/agendas/',
            json={
                'name': 'New API Agenda',
                'agenda_type': 'custom'
            },
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data['name'] == 'New API Agenda'
        assert data['todo_items_cnt'] == 0
        assert data['completed_items_cnt'] == 0
