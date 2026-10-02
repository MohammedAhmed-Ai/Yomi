import pytest
from fastapi import status
from datetime import date, timedelta
from app.db import SessionLocal
from app.models import Day

def test_get_day_success(client):
    test_date = date.today().isoformat()
    response = client.get(f"/api/days/{test_date}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["date"] == test_date
    assert "tasks" in data
    assert isinstance(data["tasks"], list)

def test_get_day_invalid_date(client):
    response = client.get("/api/days/not-a-date")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid date format" in response.json()["detail"]

def test_get_day_with_tasks(client):
    test_date = (date.today() + timedelta(days=1)).isoformat()
    
    # Create task for that date
    task_payload = {
        "title": "Day Task",
        "planned_date": test_date
    }
    res = client.post("/api/tasks/", json=task_payload)
    task_id = res.json()["id"]
    
    # Get day
    response = client.get(f"/api/days/{test_date}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert any(t["id"] == task_id for t in data["tasks"])

def test_get_day_excludes_deleted_tasks(client):
    test_date = date.today().isoformat()
    
    # Create task
    res = client.post("/api/tasks/", json={"title": "Deleted Task", "planned_date": test_date})
    task_id = res.json()["id"]
    
    # Delete it
    client.delete(f"/api/tasks/{task_id}")
    
    # Get day
    response = client.get(f"/api/days/{test_date}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert not any(t["id"] == task_id for t in data["tasks"])

def test_get_day_subtask_nesting(client):
    """Verify subtask appears nested under parent and inherits planned_date."""
    test_date = (date.today() + timedelta(days=3)).isoformat()
    
    # Create parent
    parent_res = client.post("/api/tasks/", json={"title": "Parent", "planned_date": test_date})
    parent_id = parent_res.json()["id"]
    
    # Create subtask without date
    sub_res = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent_id})
    sub_id = sub_res.json()["id"]
    
    # Get day
    response = client.get(f"/api/days/{test_date}")
    assert response.status_code == 200
    tasks = response.json()["tasks"]
    
    # Verify both exist and subtask has parent_id and date
    subtask = next(t for t in tasks if t["id"] == sub_id)
    assert subtask["parent_task_id"] == parent_id
    assert subtask["planned_date"] == test_date

def test_days_table_behavior(client):
    """Verify that creating/completing tasks doesn't create Day row, but GET /days does."""
    # 1. Create task
    client.post("/api/tasks/", json={"title": "Table Test"})
    
    with SessionLocal() as db:
        # Day table should be empty
        assert db.query(Day).count() == 0
    
    # 2. Get day
    test_date = date.today().isoformat()
    client.get(f"/api/days/{test_date}")
    
    with SessionLocal() as db:
        # Day table should now have 1 row
        assert db.query(Day).count() == 1
