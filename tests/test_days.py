from fastapi import status
from datetime import date, timedelta
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

def test_days_table_behavior(client, db_session):
    """Verify that creating/completing tasks doesn't create Day row, but GET /days does."""
    # 1. Create task
    task = client.post("/api/tasks/", json={"title": "Table Test"}).json()
    client.post(f"/api/tasks/{task['id']}/complete")

    # Day table should still be empty
    assert db_session.query(Day).count() == 0

    # 2. Get day
    test_date = date.today().isoformat()
    client.get(f"/api/days/{test_date}")

    # Day table should now have 1 row
    assert db_session.query(Day).count() == 1


def test_get_day_nests_subtasks(client):
    """Verify each task carries its subtasks tree while the day list stays flat."""
    test_date = (date.today() + timedelta(days=4)).isoformat()

    parent = client.post("/api/tasks/", json={"title": "Parent", "planned_date": test_date}).json()
    sub = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"]}).json()

    tasks = client.get(f"/api/days/{test_date}").json()["tasks"]

    # Flat list includes both parent and subtask
    assert any(t["id"] == parent["id"] for t in tasks)
    assert any(t["id"] == sub["id"] for t in tasks)

    # ...and the parent also nests its subtask
    parent_body = next(t for t in tasks if t["id"] == parent["id"])
    assert [s["id"] for s in parent_body["subtasks"]] == [sub["id"]]


def test_deleted_subtask_disappears_from_tree(client):
    """A soft-deleted subtask is hidden from both the flat list and the tree."""
    test_date = (date.today() + timedelta(days=5)).isoformat()

    parent = client.post("/api/tasks/", json={"title": "Parent", "planned_date": test_date}).json()
    sub = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"]}).json()
    client.delete(f"/api/tasks/{sub['id']}")

    tasks = client.get(f"/api/days/{test_date}").json()["tasks"]
    assert not any(t["id"] == sub["id"] for t in tasks)
    parent_body = next(t for t in tasks if t["id"] == parent["id"])
    assert parent_body["subtasks"] == []
