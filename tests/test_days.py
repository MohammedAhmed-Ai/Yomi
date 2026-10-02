import pytest
from fastapi import status
from datetime import date, timedelta

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
