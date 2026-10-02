from fastapi import status
from datetime import date, timedelta
from freezegun import freeze_time

from app.models import Tag, Task


def iso(offset_days: int = 0) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def make(client, title, planned_offset, **extra):
    payload = {"title": title, "planned_date": iso(planned_offset), **extra}
    return client.post("/api/tasks/", json=payload).json()


def run(client):
    return client.post("/api/carry-over/")


def test_pending_task_is_carried_to_today_and_original_becomes_missed(client):
    yesterday = make(client, "Overdue", -1, points=30, priority=2, notes="why")

    first = run(client)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["tasks_carried"] == 1
    assert first.json()["date"] == iso()

    today_tasks = client.get(f"/api/tasks/?planned_date={iso()}").json()
    assert len(today_tasks) == 1
    carried = today_tasks[0]

    assert carried["title"] == "Overdue"
    assert carried["notes"] == "why"
    assert carried["points"] == 30
    assert carried["priority"] == 2
    assert carried["status"] == "pending"
    assert carried["original_date"] == iso(-1)
    assert yesterday["original_date"] == iso(-1)
    assert carried["carry_count"] == 1
    assert carried["carried_from_id"] == yesterday["id"]
    assert carried["id"] != yesterday["id"]

    # The original stays on its own day, marked missed.
    original_day = client.get(f"/api/days/{iso(-1)}").json()["tasks"]
    assert [t["id"] for t in original_day] == [yesterday["id"]]
    assert original_day[0]["status"] == "missed"


def test_done_tasks_are_not_carried(client):
    done = make(client, "Finished", -1)
    client.post(f"/api/tasks/{done['id']}/complete")

    result = run(client).json()
    assert result["total_carried"] == 0
    assert client.get(f"/api/tasks/?planned_date={iso()}").json() == []
    assert client.get(f"/api/tasks/?planned_date={iso(-1)}").json()[0]["status"] == "done"


def test_running_twice_creates_no_duplicates(client):
    make(client, "Overdue", -1)
    make(client, "Also overdue", -2)

    assert run(client).json()["tasks_carried"] == 2
    assert run(client).json()["total_carried"] == 0

    today_tasks = client.get(f"/api/tasks/?planned_date={iso()}").json()
    assert sorted(t["title"] for t in today_tasks) == ["Also overdue", "Overdue"]


def test_carry_count_increases_when_carried_twice(client):
    make(client, "Persistent", -3)

    with freeze_time("2026-10-10 09:00:00"):
        run(client)
        first_copy = client.get("/api/tasks/?planned_date=2026-10-10").json()[0]
        assert first_copy["carry_count"] == 1

    # Next day the copy from the 10th is itself overdue, so it travels again.
    with freeze_time("2026-10-11 09:00:00"):
        assert run(client).json()["tasks_carried"] == 1
        second_copy = client.get("/api/tasks/?planned_date=2026-10-11").json()[0]

    assert second_copy["carry_count"] == 2
    assert second_copy["carried_from_id"] == first_copy["id"]
    # The chain of older copies is all missed now.
    assert client.get("/api/tasks/?planned_date=2026-10-10").json()[0]["status"] == "missed"


def test_locked_old_day_is_still_carried(client):
    make(client, "Frozen backlog", -1)
    assert client.patch(f"/api/days/{iso(-1)}", json={"locked": True}).status_code == 200

    result = run(client)
    assert result.status_code == status.HTTP_200_OK
    assert result.json()["tasks_carried"] == 1
    assert client.get(f"/api/tasks/?planned_date={iso()}").json()[0]["title"] == "Frozen backlog"


def test_missed_task_is_read_only(client):
    original = make(client, "Read only now", -1)
    run(client)

    for response in (
        client.patch(f"/api/tasks/{original['id']}", json={"title": "nope"}),
        client.post(f"/api/tasks/{original['id']}/complete"),
        client.post(f"/api/tasks/{original['id']}/uncomplete"),
        client.delete(f"/api/tasks/{original['id']}"),
    ):
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "read-only" in response.json()["detail"]


def test_missed_task_keeps_its_day_at_score_zero(client):
    make(client, "Missed work", -1, points=40)
    run(client)

    score = client.get(f"/api/days/{iso(-1)}/score").json()
    assert score["tasks_total"] == 1
    assert score["tasks_done"] == 0
    assert score["earned_points"] == 0
    assert score["is_complete"] is False
    assert score["score"] == 0

    # The missed original stays visible on its own day.
    day = client.get(f"/api/days/{iso(-1)}").json()
    assert [t["status"] for t in day["tasks"]] == ["missed"]


def test_pending_subtasks_are_carried_under_the_new_parent(client):
    parent = make(client, "Parent task", -1)
    sub = client.post(
        "/api/tasks/", json={"title": "Sub task", "parent_task_id": parent["id"]}
    ).json()

    result = run(client).json()
    assert result["tasks_carried"] == 1
    assert result["subtasks_carried"] == 1
    assert result["total_carried"] == 2

    carried_parent = client.get(f"/api/tasks/?planned_date={iso()}").json()[0]
    assert [s["title"] for s in carried_parent["subtasks"]] == ["Sub task"]

    carried_sub = carried_parent["subtasks"][0]
    assert carried_sub["carry_count"] == 1
    assert carried_sub["carried_from_id"] == sub["id"]
    assert carried_sub["status"] == "pending"

    original_day = client.get(f"/api/days/{iso(-1)}").json()["tasks"]
    assert {t["id"]: t["status"] for t in original_day} == {
        parent["id"]: "missed",
        sub["id"]: "missed",
    }


def test_carried_tasks_keep_their_tags(client, db_session):
    tag = Tag(name="work", color="#112233")
    db_session.add(tag)
    db_session.flush()

    parent = make(client, "Tagged parent", -1)
    sub = client.post(
        "/api/tasks/", json={"title": "Tagged sub", "parent_task_id": parent["id"]}
    ).json()
    # Keep references alive: the relationship is only appendable from a live parent.
    parent_row = db_session.get(Task, parent["id"])
    sub_row = db_session.get(Task, sub["id"])
    parent_row.tags.append(tag)
    sub_row.tags.append(tag)
    db_session.commit()

    run(client)

    carried_parent = client.get(f"/api/tasks/?planned_date={iso()}").json()[0]
    assert [t["name"] for t in carried_parent["tags"]] == ["work"]
    assert [t["name"] for t in carried_parent["subtasks"][0]["tags"]] == ["work"]


@freeze_time("2026-10-04 22:30:00")
def test_carry_over_uses_the_configured_timezone(client, monkeypatch):
    """22:30 UTC is already the 5th in Cairo, so the copy lands on a later day."""
    task = client.post("/api/tasks/", json={"title": "Late night", "planned_date": "2026-10-04"}).json()

    monkeypatch.setenv("TIMEZONE", "Africa/Cairo")
    cairo = run(client).json()
    assert cairo["date"] == "2026-10-05"
    assert cairo["tasks_carried"] == 1

    # Under UTC "today" is still the 4th, so nothing is overdue: the original is
    # already missed and the copy is planned ahead of the UTC day.
    monkeypatch.setenv("TIMEZONE", "UTC")
    utc = run(client).json()
    assert utc["date"] == "2026-10-04"
    assert utc["total_carried"] == 0
    assert client.get("/api/tasks/?planned_date=2026-10-04").json()[0]["id"] == task["id"]