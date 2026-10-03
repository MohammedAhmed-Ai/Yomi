from datetime import date, timedelta

from freezegun import freeze_time

from app.models import Day


def test_stats_range_rejects_bad_date(client):
    response = client.get("/api/stats/range?start=2026-02-30&end=2026-03-01")
    assert response.status_code == 400


def test_stats_range_rejects_start_after_end(client):
    response = client.get("/api/stats/range?start=2026-10-04&end=2026-10-03")
    assert response.status_code == 400


def test_stats_range_rejects_more_than_366_days(client):
    response = client.get("/api/stats/range?start=2025-01-01&end=2026-01-02")
    assert response.status_code == 400


def test_stats_range_empty_day_is_excluded_from_completion_average(client):
    today = date.today()
    empty_date = today - timedelta(days=1)
    task_date = today
    with freeze_time(task_date.isoformat()):
        task_a = client.post(
            "/api/tasks/", json={"title": "A", "planned_date": task_date.isoformat()}
        ).json()
        client.post(
            "/api/tasks/", json={"title": "B", "planned_date": task_date.isoformat()}
        )
        client.post(f"/api/tasks/{task_a['id']}/complete")

    response = client.get(
        f"/api/stats/range?start={empty_date.isoformat()}&end={task_date.isoformat()}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["days"][0]["is_empty"] is True
    assert data["days"][0]["completion_pct"] == 0
    assert data["days"][1]["completion_pct"] == 50
    assert data["summary"]["days_with_tasks"] == 1
    assert data["summary"]["avg_completion_pct"] == 50


def test_stats_range_scores_fully_done_and_partial_days(client):
    full_date = date(2026, 10, 1)
    partial_date = date(2026, 10, 2)
    with freeze_time(full_date.isoformat()):
        full_a = client.post(
            "/api/tasks/", json={"title": "Full A", "planned_date": full_date.isoformat(), "points": 30}
        ).json()
        full_b = client.post(
            "/api/tasks/", json={"title": "Full B", "planned_date": full_date.isoformat(), "points": 70}
        ).json()
        client.post(f"/api/tasks/{full_a['id']}/complete")
        client.post(f"/api/tasks/{full_b['id']}/complete")

    with freeze_time(partial_date.isoformat()):
        partial_a = client.post(
            "/api/tasks/", json={"title": "Partial A", "planned_date": partial_date.isoformat(), "points": 40}
        ).json()
        client.post(
            "/api/tasks/", json={"title": "Partial B", "planned_date": partial_date.isoformat(), "points": 60}
        )
        client.post(f"/api/tasks/{partial_a['id']}/complete")

    response = client.get(
        f"/api/stats/range?start={full_date.isoformat()}&end={partial_date.isoformat()}"
    )
    assert response.status_code == 200
    full, partial = response.json()["days"]
    assert (full["tasks_total"], full["tasks_done"], full["total_points"]) == (2, 2, 100)
    assert (full["earned_points"], full["completion_pct"], full["score"]) == (100, 100, 100)
    assert full["is_complete"] is True
    assert (partial["tasks_total"], partial["tasks_done"], partial["total_points"]) == (2, 1, 100)
    assert (partial["earned_points"], partial["completion_pct"], partial["score"]) == (40, 50, 0)
    assert partial["is_complete"] is False


def test_stats_range_matches_day_score(client):
    target_date = date.today()
    with freeze_time(target_date.isoformat()):
        task = client.post(
            "/api/tasks/", json={"title": "Task", "planned_date": target_date.isoformat(), "points": 25}
        ).json()
        client.post(f"/api/tasks/{task['id']}/complete")

    range_day = client.get(
        f"/api/stats/range?start={target_date.isoformat()}&end={target_date.isoformat()}"
    ).json()["days"][0]
    day_score = client.get(f"/api/days/{target_date.isoformat()}/score").json()
    for field in (
        "tasks_total",
        "tasks_done",
        "total_points",
        "earned_points",
        "score",
        "is_complete",
        "is_empty",
    ):
        assert range_day[field] == day_score[field]
    assert range_day["completion_pct"] == 100


def test_stats_range_does_not_create_day_rows(client, db_session):
    target_date = date.today()
    response = client.get(
        f"/api/stats/range?start={target_date.isoformat()}&end={target_date.isoformat()}"
    )
    assert response.status_code == 200
    assert db_session.query(Day).count() == 0


def test_deleted_task_is_excluded_from_day_score_and_range(client):
    target_date = date.today()
    task = client.post(
        "/api/tasks/",
        json={"title": "Deleted", "planned_date": target_date.isoformat()},
    ).json()
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204

    day = target_date.isoformat()
    assert client.get(f"/api/days/{day}").json()["tasks"] == []
    assert client.get(f"/api/days/{day}/score").json()["tasks_total"] == 0
    range_day = client.get(
        f"/api/stats/range?start={day}&end={day}"
    ).json()["days"][0]
    assert range_day["tasks_total"] == 0
