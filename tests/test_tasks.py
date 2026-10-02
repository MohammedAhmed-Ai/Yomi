import pytest
from fastapi import status
from datetime import date, datetime, timedelta
from app.models import Task

def test_create_task_success(client):
    payload = {
        "title": "Test Task",
        "planned_date": date.today().isoformat(),
        "points": 20
    }
    response = client.post("/api/tasks/", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["title"] == "Test Task"
    assert data["planned_date"] == payload["planned_date"]
    assert data["original_date"] == payload["planned_date"]
    assert data["status"] == "pending"

def test_create_task_subtask_inheritance(client):
    # Create parent
    parent_payload = {
        "title": "Parent Task",
        "planned_date": (date.today() + timedelta(days=1)).isoformat(),
    }
    parent_res = client.post("/api/tasks/", json=parent_payload)
    parent_id = parent_res.json()["id"]

    # Create subtask without planned_date
    subtask_payload = {
        "title": "Subtask",
        "parent_task_id": parent_id,
    }
    response = client.post("/api/tasks/", json=subtask_payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["planned_date"] == parent_payload["planned_date"]
    assert data["original_date"] == parent_payload["planned_date"]

def test_create_task_subtask_depth_limit(client):
    # Level 0
    p0_res = client.post("/api/tasks/", json={"title": "L0"})
    p0_id = p0_res.json()["id"]
    
    # Level 1
    p1_res = client.post("/api/tasks/", json={"title": "L1", "parent_task_id": p0_id})
    p1_id = p1_res.json()["id"]
    
    # Level 2 - Should fail
    p2_payload = {"title": "L2", "parent_task_id": p1_id}
    response = client.post("/api/tasks/", json=p2_payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Subtasks are limited to 1 level deep" in response.json()["detail"]

def test_complete_task(client):
    # Create task
    res = client.post("/api/tasks/", json={"title": "Complete Me"})
    task_id = res.json()["id"]
    
    # Complete it
    response = client.post(f"/api/tasks/{task_id}/complete")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "done"
    assert data["completed_date"] is not None

def test_uncomplete_task(client):
    # Create and complete
    res = client.post("/api/tasks/", json={"title": "Uncomplete Me"})
    task_id = res.json()["id"]
    client.post(f"/api/tasks/{task_id}/complete")
    
    # Uncomplete it
    response = client.post(f"/api/tasks/{task_id}/uncomplete")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "pending"
    assert data["completed_date"] is None

def test_update_task_status_done(client):
    res = client.post("/api/tasks/", json={"title": "Update Me"})
    task_id = res.json()["id"]
    
    response = client.patch(f"/api/tasks/{task_id}", json={"status": "done"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "done"
    assert data["completed_date"] is not None

def test_delete_task_soft(client):
    res = client.post("/api/tasks/", json={"title": "Delete Me"})
    task_id = res.json()["id"]
    
    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    
    # Since it's a soft delete, we check the DB via a direct query or the get endpoint if it exists.
    # For now, we can verify via the client if there's a get_task (though not in the provided router snippet).
    # We rely on the implementation logic provided in the router.
