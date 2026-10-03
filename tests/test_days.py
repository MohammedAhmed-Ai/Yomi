from fastapi import status
from datetime import date, timedelta
from freezegun import freeze_time

from app.models import Day


def iso(offset_days: int = 0) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def test_get_day_success(client):
    response = client.get(f"/api/days/{iso()}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["date"] == iso()
    assert isinstance(data["tasks"], list)


def test_get_day_invalid_date(client):
    response = client.get("/api/days/not-a-date")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid date format" in response.json()["detail"]


def test_get_day_with_tasks(client):
    test_date = iso(1)
    res = client.post("/api/tasks/", json={"title": "Day Task", "planned_date": test_date})
    task_id = res.json()["id"]

    tasks = client.get(f"/api/days/{test_date}").json()["tasks"]
    assert any(t["id"] == task_id for t in tasks)


def test_get_day_excludes_deleted_tasks(client):
    res = client.post("/api/tasks/", json={"title": "Deleted Task", "planned_date": iso()})
    task_id = res.json()["id"]
    client.delete(f"/api/tasks/{task_id}")

    tasks = client.get(f"/api/days/{iso()}").json()["tasks"]
    assert not any(t["id"] == task_id for t in tasks)


def test_get_day_subtask_nesting(client):
    """Verify subtask appears with its parent link and inherits planned_date."""
    test_date = iso(3)
    parent_id = client.post(
        "/api/tasks/", json={"title": "Parent", "planned_date": test_date}
    ).json()["id"]
    sub_id = client.post(
        "/api/tasks/", json={"title": "Sub", "parent_task_id": parent_id}
    ).json()["id"]

    tasks = client.get(f"/api/days/{test_date}").json()["tasks"]

    subtask = next(t for t in tasks if t["id"] == sub_id)
    assert subtask["parent_task_id"] == parent_id
    assert subtask["planned_date"] == test_date


def test_days_table_behavior(client, db_session):
    """Verify that creating/completing tasks doesn't create Day row, but GET /days does."""
    task = client.post("/api/tasks/", json={"title": "Table Test"}).json()
    client.post(f"/api/tasks/{task['id']}/complete")

    assert db_session.query(Day).count() == 0

    client.get(f"/api/days/{iso()}")

    assert db_session.query(Day).count() == 1


def test_get_day_nests_subtasks(client):
    """Verify each task carries its subtasks tree while the day list stays flat."""
    test_date = iso(4)
    parent = client.post("/api/tasks/", json={"title": "Parent", "planned_date": test_date}).json()
    sub = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"]}).json()

    tasks = client.get(f"/api/days/{test_date}").json()["tasks"]

    assert any(t["id"] == parent["id"] for t in tasks)
    assert any(t["id"] == sub["id"] for t in tasks)

    parent_body = next(t for t in tasks if t["id"] == parent["id"])
    assert [s["id"] for s in parent_body["subtasks"]] == [sub["id"]]


def test_deleted_subtask_disappears_from_tree(client):
    """A soft-deleted subtask is hidden from both the flat list and the tree."""
    test_date = iso(5)
    parent = client.post("/api/tasks/", json={"title": "Parent", "planned_date": test_date}).json()
    sub = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"]}).json()
    client.delete(f"/api/tasks/{sub['id']}")

    tasks = client.get(f"/api/days/{test_date}").json()["tasks"]
    assert not any(t["id"] == sub["id"] for t in tasks)
    parent_body = next(t for t in tasks if t["id"] == parent["id"])
    assert parent_body["subtasks"] == []


# --- day lifecycle ---

def test_start_day_sets_started_at(client, db_session):
    res = client.post(f"/api/days/{iso()}/start")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["started_at"] is not None
    assert db_session.query(Day).count() == 1


def test_start_day_is_idempotent(client):
    first = client.post(f"/api/days/{iso()}/start").json()
    second = client.post(f"/api/days/{iso()}/start").json()
    assert first["started_at"] == second["started_at"]


def test_start_day_invalid_date(client):
    assert client.post("/api/days/nope/start").status_code == status.HTTP_400_BAD_REQUEST


def test_patch_day_saves_reflection_and_mood(client):
    res = client.patch(f"/api/days/{iso()}", json={"reflection": "Focused day", "mood": 5})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["reflection"] == "Focused day"
    assert res.json()["mood"] == 5


def test_patch_day_partial_update_keeps_other_fields(client):
    client.patch(f"/api/days/{iso()}", json={"reflection": "Kept", "mood": 5})
    res = client.patch(f"/api/days/{iso()}", json={"mood": 5}).json()
    assert res["reflection"] == "Kept"
    assert res["mood"] == 5


def test_patch_day_mood_validation(client):
    assert client.patch(f"/api/days/{iso()}", json={"mood": 0}).status_code == 422
    assert client.patch(f"/api/days/{iso()}", json={"mood": 6}).status_code == 422
    assert client.patch(f"/api/days/{iso()}", json={"locked": "maybe"}).status_code == 422


def test_mood_five_is_accepted_and_six_is_rejected(client):
    assert client.patch(f"/api/days/{iso()}", json={"mood": 5}).status_code == 200
    assert client.patch(f"/api/days/{iso()}", json={"mood": 6}).status_code == 422


def test_mood_can_be_cleared(client):
    response = client.patch(f"/api/days/{iso()}", json={"mood": None})
    assert response.status_code == 200
    assert response.json()["mood"] is None


def test_patch_day_rejects_unknown_fields(client):
    assert client.patch(f"/api/days/{iso()}", json={"score": 100}).status_code == 422


# --- day lock ---

def test_lock_blocks_task_mutations(client):
    test_date = iso(6)
    task = client.post("/api/tasks/", json={"title": "Frozen", "planned_date": test_date}).json()
    assert client.patch(f"/api/days/{test_date}", json={"locked": True}).status_code == 200

    assert client.post(f"/api/tasks/{task['id']}/complete").status_code == 423
    # Even a no-op uncomplete is rejected: the day is frozen, not merely unchanged.
    assert client.post(f"/api/tasks/{task['id']}/uncomplete").status_code == 423
    assert client.patch(f"/api/tasks/{task['id']}", json={"title": "Nope"}).status_code == 423
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 423
    assert client.post(
        "/api/tasks/", json={"title": "Late", "planned_date": test_date}
    ).status_code == 423


def test_lock_blocks_completing_an_already_done_task(client):
    test_date = iso(16)
    task = client.post("/api/tasks/", json={"title": "Done", "planned_date": test_date}).json()
    client.post(f"/api/tasks/{task['id']}/complete")
    client.patch(f"/api/days/{test_date}", json={"locked": True})

    assert client.post(f"/api/tasks/{task['id']}/complete").status_code == 423


def test_unlock_restores_task_mutations(client):
    test_date = iso(7)
    task = client.post("/api/tasks/", json={"title": "Thawed", "planned_date": test_date}).json()
    client.patch(f"/api/days/{test_date}", json={"locked": True})
    client.patch(f"/api/days/{test_date}", json={"locked": False})

    assert client.post(f"/api/tasks/{task['id']}/complete").status_code == 200


def test_lock_allows_reflection_edits(client):
    """A locked day freezes its tasks, not the user's own notes."""
    test_date = iso(8)
    client.patch(f"/api/days/{test_date}", json={"locked": True})
    res = client.patch(f"/api/days/{test_date}", json={"reflection": "Post-mortem", "mood": 5})
    assert res.status_code == 200
    assert res.json()["reflection"] == "Post-mortem"


def test_lock_only_affects_its_own_day(client):
    locked_date, free_date = iso(9), iso(10)
    client.patch(f"/api/days/{locked_date}", json={"locked": True})
    task = client.post("/api/tasks/", json={"title": "Other day", "planned_date": free_date}).json()

    assert client.post(f"/api/tasks/{task['id']}/complete").status_code == 200


# --- daily score ---

def test_score_of_empty_day(client):
    res = client.get(f"/api/days/{iso()}/score")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["is_empty"] is True
    assert data["is_complete"] is False
    assert data["score"] == 0
    assert data["total_points"] == 0


def test_score_does_not_create_day_row(client, db_session):
    client.get(f"/api/days/{iso()}/score")
    assert db_session.query(Day).count() == 0


@freeze_time("2026-10-01 10:00:00")
def test_score_is_all_or_nothing(client):
    test_date = iso()
    a = client.post("/api/tasks/", json={"title": "A", "planned_date": test_date, "points": 30}).json()
    client.post("/api/tasks/", json={"title": "B", "planned_date": test_date, "points": 70})
    client.post(f"/api/tasks/{a['id']}/complete")

    partial = client.get(f"/api/days/{test_date}/score").json()
    assert partial["tasks_total"] == 2
    assert partial["tasks_done"] == 1
    assert partial["earned_points"] == 30
    assert partial["total_points"] == 100
    assert partial["is_complete"] is False
    assert partial["score"] == 0

    for task in client.get(f"/api/tasks/?planned_date={test_date}").json():
        client.post(f"/api/tasks/{task['id']}/complete")

    full = client.get(f"/api/days/{test_date}/score").json()
    assert full["is_complete"] is True
    assert full["earned_points"] == 100
    assert full["score"] == 100


@freeze_time("2026-10-02 10:00:00")
def test_score_counts_late_completion_as_miss(client):
    """A task finished on a later day does not count for the day it was planned on."""
    planned = "2026-10-01"
    task = client.post("/api/tasks/", json={"title": "Late", "planned_date": planned}).json()
    client.post(f"/api/tasks/{task['id']}/complete")

    missed = client.get(f"/api/days/{planned}/score").json()
    assert missed["tasks_total"] == 1
    assert missed["tasks_done"] == 0
    assert missed["earned_points"] == 0
    assert missed["is_complete"] is False
    assert missed["score"] == 0

    # The work happened, just not on the day it belonged to.
    assert client.get("/api/days/2026-10-02/score").json()["tasks_total"] == 0


@freeze_time("2026-10-01 10:00:00")
def test_score_ignores_subtasks_in_totals(client):
    test_date = iso()
    parent = client.post(
        "/api/tasks/", json={"title": "Parent", "planned_date": test_date, "points": 40}
    ).json()
    sub = client.post(
        "/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"], "points": 5}
    ).json()
    client.post(f"/api/tasks/{sub['id']}/complete")

    data = client.get(f"/api/days/{test_date}/score").json()
    assert data["tasks_total"] == 1
    assert data["tasks_done"] == 0
    assert data["total_points"] == 40
    assert data["subtasks_total"] == 1
    assert data["subtasks_done"] == 1
    assert data["score"] == 0

    client.post(f"/api/tasks/{parent['id']}/complete")
    assert client.get(f"/api/days/{test_date}/score").json()["score"] == 40


def test_score_ignores_deleted_tasks(client):
    test_date = iso(15)
    task = client.post("/api/tasks/", json={"title": "Dropped", "planned_date": test_date}).json()
    client.delete(f"/api/tasks/{task['id']}")

    data = client.get(f"/api/days/{test_date}/score").json()
    assert data["is_empty"] is True
    assert data["tasks_total"] == 0


def test_score_invalid_date(client):
    assert client.get("/api/days/not-a-date/score").status_code == status.HTTP_400_BAD_REQUEST