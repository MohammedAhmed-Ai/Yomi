from fastapi import status
from datetime import date, timedelta
from freezegun import freeze_time
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

def test_create_task_original_date(client):
    """Verify that original_date equals planned_date on create."""
    planned = (date.today() + timedelta(days=2)).isoformat()
    payload = {"title": "Original Date Test", "planned_date": planned}
    response = client.post("/api/tasks/", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["original_date"] == planned
    assert data["planned_date"] == planned

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

def test_create_task_subtask_rejected(client):
    """Explicitly verify subtask of a subtask is rejected (4xx)."""
    # Level 0
    p0 = client.post("/api/tasks/", json={"title": "L0"}).json()
    # Level 1
    p1 = client.post("/api/tasks/", json={"title": "L1", "parent_task_id": p0["id"]}).json()
    # Level 2
    res = client.post("/api/tasks/", json={"title": "L2", "parent_task_id": p1["id"]})
    assert res.status_code == 400

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

def test_complete_task_twice_noop(client):
    """Verify completing a task twice keeps the original completion stamps."""
    res = client.post("/api/tasks/", json={"title": "Double Complete"})
    task_id = res.json()["id"]

    # First time
    first_res = client.post(f"/api/tasks/{task_id}/complete")
    first_date = first_res.json()["completed_date"]
    first_at = first_res.json()["completed_at"]

    # Second time
    second_res = client.post(f"/api/tasks/{task_id}/complete")
    second_date = second_res.json()["completed_date"]

    assert first_date == second_date
    assert second_res.json()["completed_at"] == first_at
    assert second_res.status_code == status.HTTP_200_OK


def test_uncomplete_twice_noop(client):
    res = client.post("/api/tasks/", json={"title": "Double Uncomplete"}).json()
    client.post(f"/api/tasks/{res['id']}/complete")

    client.post(f"/api/tasks/{res['id']}/uncomplete")
    second = client.post(f"/api/tasks/{res['id']}/uncomplete").json()

    assert second["status"] == "pending"
    assert second["completed_at"] is None
    assert second["completed_date"] is None

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

def test_uncomplete_clears_dates(client):
    """Verify uncomplete clears completed_at and completed_date."""
    res = client.post("/api/tasks/", json={"title": "Clear Dates"})
    task_id = res.json()["id"]
    client.post(f"/api/tasks/{task_id}/complete")
    
    response = client.post(f"/api/tasks/{task_id}/uncomplete")
    data = response.json()
    assert data["completed_at"] is None
    assert data["completed_date"] is None

def test_update_task_title_points(client):
    res = client.post("/api/tasks/", json={"title": "Update Me"})
    task_id = res.json()["id"]
    
    payload = {"title": "Updated Title", "points": 50}
    response = client.patch(f"/api/tasks/{task_id}", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["points"] == 50


def _make_missed_task(client):
    task = client.post(
        "/api/tasks/",
        json={
            "title": "Missed task",
            "planned_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    ).json()
    assert client.post("/api/carry-over/").status_code == 200
    return task


def test_missed_task_accepts_miss_reason_patch(client):
    task = _make_missed_task(client)
    response = client.patch(
        f"/api/tasks/{task['id']}", json={"miss_reason": "tired"}
    )
    assert response.status_code == 200
    assert response.json()["miss_reason"] == "tired"


def test_carried_copy_includes_original_miss_reason(client):
    task = _make_missed_task(client)
    reason = client.patch(
        f"/api/tasks/{task['id']}", json={"miss_reason": "too_big"}
    )
    assert reason.status_code == 200

    carried = client.get(f"/api/days/{date.today().isoformat()}").json()["tasks"]
    copy = next(item for item in carried if item["carried_from_id"] == task["id"])
    assert copy["source_miss_reason"] == "too_big"


def test_missed_task_rejects_other_patch_fields(client):
    task = _make_missed_task(client)
    response = client.patch(f"/api/tasks/{task['id']}", json={"title": "Changed"})
    assert response.status_code == 409


def test_missed_task_rejects_invalid_miss_reason(client):
    task = _make_missed_task(client)
    response = client.patch(
        f"/api/tasks/{task['id']}", json={"miss_reason": "not-a-reason"}
    )
    assert response.status_code == 422


def test_missed_task_miss_reason_can_be_cleared(client):
    task = _make_missed_task(client)
    client.patch(f"/api/tasks/{task['id']}", json={"miss_reason": "other"})
    response = client.patch(f"/api/tasks/{task['id']}", json={"miss_reason": None})
    assert response.status_code == 200
    assert response.json()["miss_reason"] is None


def test_missed_task_reason_can_be_edited_on_a_locked_day(client):
    task = client.post(
        "/api/tasks/",
        json={
            "title": "Locked missed task",
            "planned_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    ).json()
    planned_date = (date.today() - timedelta(days=1)).isoformat()
    assert client.patch(f"/api/days/{planned_date}", json={"locked": True}).status_code == 200
    assert client.post("/api/carry-over/").status_code == 200
    response = client.patch(
        f"/api/tasks/{task['id']}", json={"miss_reason": "no_time"}
    )
    assert response.status_code == 200
    assert response.json()["miss_reason"] == "no_time"


@freeze_time("2026-10-01 22:30:00")
def test_completed_date_cairo(client):
    """Verify completed_date uses the Cairo date (22:30 UTC is already the next day in Cairo)."""
    # Cairo is UTC+2 (EEST in October). 22:30 UTC on Oct 1st is 00:30 on Oct 2nd.
    res = client.post("/api/tasks/", json={"title": "Cairo Test"})
    task_id = res.json()["id"]

    data = client.post(f"/api/tasks/{task_id}/complete").json()

    assert data["completed_date"] == date(2026, 10, 2).isoformat()
    assert data["completed_at"].startswith("2026-10-01T22:30:00")


@freeze_time("2026-10-01 22:30:00")
def test_completed_date_respects_timezone_env(client, monkeypatch):
    """Same instant, different TIMEZONE -> different calendar day."""
    res = client.post("/api/tasks/", json={"title": "TZ Test"}).json()
    task_id = res["id"]

    monkeypatch.setenv("TIMEZONE", "Africa/Cairo")
    cairo = client.post(f"/api/tasks/{task_id}/complete").json()

    monkeypatch.setenv("TIMEZONE", "UTC")
    utc = client.post(f"/api/tasks/{task_id}/uncomplete").json()
    utc = client.post(f"/api/tasks/{task_id}/complete").json()

    assert cairo["completed_date"] == "2026-10-02"
    assert utc["completed_date"] == "2026-10-01"

def test_delete_task_soft(client):
    res = client.post("/api/tasks/", json={"title": "Delete Me"})
    task_id = res.json()["id"]
    
    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    
    # Since it's a soft delete, we check the DB via a direct query or the get endpoint if it exists.
    # For now, we can verify via the client if there's a get_task (though not in the provided router snippet).
    # We rely on the implementation logic provided in the router.

def test_soft_delete_propagation(client, db_session):
    """Verify soft delete hides task and subtasks from day, but rows stay in DB."""
    # Create parent and subtask
    parent = client.post("/api/tasks/", json={"title": "Parent"}).json()
    sub = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"]}).json()
    test_date = date.today().isoformat()

    # Soft delete parent
    client.delete(f"/api/tasks/{parent['id']}")

    # Get day - neither should appear
    response = client.get(f"/api/days/{test_date}")
    tasks = response.json()["tasks"]
    assert not any(t["id"] == parent["id"] for t in tasks)
    assert not any(t["id"] == sub["id"] for t in tasks)

    # Verify rows still exist in DB, both flagged as deleted
    for task_id in (parent["id"], sub["id"]):
        row = db_session.get(Task, task_id)
        assert row is not None
        assert row.status == "deleted"
        assert row.deleted_at is not None


def test_subtask_delete_does_not_touch_parent(client, db_session):
    parent = client.post("/api/tasks/", json={"title": "Parent"}).json()
    sub = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"]}).json()

    client.delete(f"/api/tasks/{sub['id']}")

    assert db_session.get(Task, sub["id"]).status == "deleted"
    assert db_session.get(Task, parent["id"]).status == "pending"


def test_create_task_rejects_client_lifecycle_fields(client, db_session):
    """Status is server-owned: a client cannot create an already-done task."""
    res = client.post(
        "/api/tasks/",
        json={"title": "Sneaky", "status": "done", "completed_date": "2026-01-01"},
    )
    assert res.status_code == 422
    assert db_session.query(Task).count() == 0


def test_patch_cannot_change_status(client):
    res = client.post("/api/tasks/", json={"title": "Patch Me"}).json()
    response = client.patch(f"/api/tasks/{res['id']}", json={"status": "done"})
    assert response.status_code == 422


def test_list_tasks_sorted_and_excludes_deleted(client):
    test_date = (date.today() + timedelta(days=6)).isoformat()
    b = client.post("/api/tasks/", json={"title": "B", "planned_date": test_date, "sort_order": 2}).json()
    a = client.post("/api/tasks/", json={"title": "A", "planned_date": test_date, "sort_order": 1}).json()
    gone = client.post("/api/tasks/", json={"title": "Gone", "planned_date": test_date}).json()
    client.delete(f"/api/tasks/{gone['id']}")

    ids = [t["id"] for t in client.get(f"/api/tasks/?planned_date={test_date}").json()]
    assert ids == [a["id"], b["id"]]

def test_edit_deleted_or_unknown_task(client):
    """Verify editing, completing or deleting a deleted or unknown task returns 404."""
    # Create and delete
    res = client.post("/api/tasks/", json={"title": "Ghost"})
    task_id = res.json()["id"]
    client.delete(f"/api/tasks/{task_id}")
    
    # Edit
    res_edit = client.patch(f"/api/tasks/{task_id}", json={"title": "New"})
    assert res_edit.status_code == 404
    
    # Complete
    res_comp = client.post(f"/api/tasks/{task_id}/complete")
    assert res_comp.status_code == 404
    
    # Delete
    res_del = client.delete(f"/api/tasks/{task_id}")
    assert res_del.status_code == 404
    
    # Unknown
    res_unk = client.patch("/api/tasks/99999", json={"title": "New"})
    assert res_unk.status_code == 404

def test_create_task_validation_errors(client):
    """Verify validation errors for empty title, points 5000, priority 9."""
    # Empty title
    res = client.post("/api/tasks/", json={"title": "", "points": 10})
    assert res.status_code == 422
    
    # Points too high
    res = client.post("/api/tasks/", json={"title": "High Points", "points": 5000})
    assert res.status_code == 422
    
    # Priority too high
    res = client.post("/api/tasks/", json={"title": "High Priority", "priority": 9})
    assert res.status_code == 422
