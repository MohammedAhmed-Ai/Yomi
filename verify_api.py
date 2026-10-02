import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_tags_flow():
    # Test Create Tag
    tag_name = "TestTag"
    response = client.post("/api/tags", json={"name": tag_name})
    assert response.status_code == 200
    created_tag = response.json()
    assert created_tag["name"] == tag_name
    tag_id = created_tag["id"]

    # Test Duplicate Tag (409 Conflict)
    response = client.post("/api/tags", json={"name": tag_name})
    assert response.status_code == 409

    # Test List Tags
    response = client.get("/api/tags")
    assert response.status_code == 200
    assert any(tag["name"] == tag_name for tag in response.json())

def test_days_flow():
    # Test Get Day (should auto-create)
    response = client.get("/api/days/2026-10-02")
    assert response.status_code == 200
    assert response.json()["date"] == "2026-10-02"

def test_tasks_flow():
    # Create a Day first to ensure it exists
    client.get("/api/days/2026-10-02")
    
    # Test Create Task
    task_data = {
        "title": "Verification Task",
        "date": "2026-10-02",
        "status": "todo"
    }
    response = client.post("/api/tasks", json=task_data)
    assert response.status_code == 200
    task_id = response.json()["id"]

    # Test Create Subtask (1 level)
    subtask_data = {
        "title": "Subtask 1",
        "date": "2026-10-02",
        "parent_task_id": task_id,
        "status": "todo"
    }
    response = client.post("/api/tasks", json=subtask_data)
    assert response.status_code == 200
    subtask_id = response.json()["id"]

    # Test Subtask Depth Limit (2nd level should fail)
    deep_subtask_data = {
        "title": "Deep Subtask",
        "date": "2026-10-02",
        "parent_task_id": subtask_id,
        "status": "todo"
    }
    response = client.post("/api/tasks", json=deep_subtask_data)
    assert response.status_code == 400
    assert "maximum depth" in response.json()["detail"].lower()

if __name__ == "__main__":
    try:
        test_health()
        test_tags_flow()
        test_days_flow()
        test_tasks_flow()
        print("✅ API Verification Successful: All flows passed.")
    except Exception as e:
        print(f"❌ API Verification Failed: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
