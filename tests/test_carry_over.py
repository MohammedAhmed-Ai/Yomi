from fastapi import status
from contextlib import contextmanager
from datetime import date, timedelta
from typing import NamedTuple
from freezegun import freeze_time
import pytest
from sqlalchemy import event, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.models import Tag, Task, TaskTag, utcnow
from app.time_utils import local_date


# A carry-over must touch the whole backlog in a fixed number of statements, so
# this is the ceiling the N+1 regression test below enforces.
MAX_CARRY_OVER_STATEMENTS = 12


def iso(offset_days: int = 0) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def make(client, title, planned_offset, **extra):
    payload = {"title": title, "planned_date": iso(planned_offset), **extra}
    return client.post("/api/tasks/", json=payload).json()


def run(client):
    return client.post("/api/carry-over/")


@contextmanager
def count_statements(engine):
    """Record every SQL statement the engine emits inside the block."""
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


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


def test_carried_task_response_includes_source_id(client):
    original = make(client, "With source", -1)
    assert run(client).status_code == status.HTTP_200_OK
    carried = client.get(f"/api/tasks/?planned_date={iso()}").json()[0]
    assert carried["carried_from_id"] == original["id"]


def test_unique_carried_from_index_rejects_duplicate_copy(client, db_session):
    original = make(client, "Unique source", -1)
    db_session.add(Task(title="First copy", carried_from_id=original["id"]))
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(Task(title="Duplicate copy", carried_from_id=original["id"]))
            db_session.flush()


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


def test_carry_over_does_not_issue_a_query_per_task(client, db_session):
    """Carrying a backlog must not cost a query per task (N+1 regression guard).

    Existence of an existing copy used to be checked once per task and once per
    subtask, so a 200-task backlog cost 200 extra SELECTs. It must stay flat.
    """
    roots, subtasks_per_root = 50, 3
    for i in range(roots):
        parent = make(client, f"Backlog {i}", -1 - (i % 5))
        for s in range(subtasks_per_root):
            client.post(
                "/api/tasks/",
                json={
                    "title": f"Backlog {i} sub {s}",
                    "parent_task_id": parent["id"],
                },
            )

    with count_statements(db_session.get_bind()) as statements:
        result = run(client)

    assert result.status_code == status.HTTP_200_OK
    assert result.json()["tasks_carried"] == roots
    assert result.json()["subtasks_carried"] == roots * subtasks_per_root
    assert result.json()["total_carried"] == roots * (1 + subtasks_per_root)
    assert len(statements) <= MAX_CARRY_OVER_STATEMENTS, (
        f"{len(statements)} statements for {roots} tasks:\n"
        + "\n".join(f"  {s.splitlines()[0][:90]}" for s in statements)
    )


def test_query_count_does_not_grow_with_backlog_size(client, db_session):
    """A larger backlog must not add queries, only rows."""
    def measure(roots: int) -> int:
        for i in range(roots):
            parent = make(client, f"Batch {i}", -1 - (i % 5))
            client.post(
                "/api/tasks/",
                json={"title": f"Batch {i} sub", "parent_task_id": parent["id"]},
            )
        with count_statements(db_session.get_bind()) as statements:
            assert run(client).status_code == status.HTTP_200_OK
        return len(statements)

    small = measure(5)
    large = measure(45)

    assert large <= MAX_CARRY_OVER_STATEMENTS
    assert large == small


# ---------------------------------------------------------------------------
# Helpers shared by the behaviour tests below
# ---------------------------------------------------------------------------

# The columns that describe the *work* rather than the day it sits on. A carried
# copy must reproduce these from its source byte for byte.
COPIED_VERBATIM = ("title", "notes", "points", "priority", "sort_order", "original_date")

# Every column except the one carry-over is allowed to change on a source.
SOURCE_UNCHANGED = tuple(c.name for c in Task.__table__.c if c.name != "status")


def task_rows(db_session) -> dict[int, dict]:
    """Every task row as a plain dict, keyed by id.

    Read through Core rather than the ORM on purpose: carry-over writes with Core
    DML, so the session's identity map still holds the pre-carry-over `pending`
    status of the sources and would hide what the endpoint actually wrote.
    """
    return {
        row.id: dict(row._mapping)
        for row in db_session.execute(select(Task.__table__)).all()
    }


def tag_ids_by_task(db_session) -> dict[int, list[int]]:
    """Sorted tag ids per task, read straight from the link table.

    Every task gets an entry, so an untagged task reads as `[]` rather than
    missing and a tag that was dropped looks like a difference.
    """
    links: dict[int, list[int]] = {}
    for task_id, tag_id in db_session.execute(
        select(TaskTag.task_id, TaskTag.tag_id).order_by(TaskTag.task_id, TaskTag.tag_id)
    ).all():
        links.setdefault(task_id, []).append(tag_id)
    task_ids = db_session.execute(select(Task.__table__.c.id)).scalars().all()
    return {task_id: links.get(task_id, []) for task_id in task_ids}


def copies_by_source(db_session) -> dict[int, dict]:
    """source id -> the single row carried from it.

    Fails the test outright if a source ever has two copies, which is the
    duplication that the unique index and the retry below exist to prevent.
    """
    by_source: dict[int, dict] = {}
    for row in task_rows(db_session).values():
        source_id = row["carried_from_id"]
        if source_id is None:
            continue
        assert source_id not in by_source, f"two copies of task {source_id}"
        by_source[source_id] = row
    return by_source


def assert_fields_equal(copy: dict, source: dict, fields, label: str) -> None:
    """Compare field by field, so a failure names the field that drifted."""
    drift = {f: {"copy": copy[f], "source": source[f]} for f in fields if copy[f] != source[f]}
    assert not drift, f"{label}: {drift}"


def set_tags(db_session, task_id: int, tag_ids: list[int]) -> None:
    task = db_session.get(Task, task_id)
    task.tags[:] = [db_session.get(Tag, tag_id) for tag_id in tag_ids]


# ---------------------------------------------------------------------------
# 1. Field by field: a copy is the same work on a new day
# ---------------------------------------------------------------------------


def test_carried_copy_reproduces_its_source_field_by_field(client, db_session):
    """Every field the copy is supposed to inherit, inherited; the source untouched.

    Differentiates points, priority, notes and sort_order on purpose (including
    the falsy 0/""/None cases, which a truthiness bug would quietly drop) and
    covers untagged roots, multi-tag roots and untagged subtasks.
    """
    db_session.add_all(
        [Tag(name="alpha", color="#111111"), Tag(name="beta", color="#222222")]
    )
    db_session.commit()
    tag_ids = dict(db_session.execute(select(Tag.name, Tag.id)).all())

    roots_spec = [
        dict(title="Ship release", points=30, priority=3, notes="why it matters",
             sort_order=5, tags=["alpha"]),
        dict(title="Write it up", points=0, priority=0, notes=None,
             sort_order=0, tags=[]),
        dict(title="Empty notes, last in the day", points=1000, priority=1, notes="",
             sort_order=99, tags=["alpha", "beta"]),
        dict(title="مرحبا 'quoted' ; drop table tasks", points=7, priority=2,
             notes="line one\nline two", sort_order=13, tags=["beta"]),
    ]
    subs_spec = {
        "Ship release": [
            dict(title="Deploy", points=5, priority=0, notes=None,
                 sort_order=1, tags=[]),
            dict(title="Smoke test", points=7, priority=2, notes="run it twice",
                 sort_order=2, tags=["beta"]),
        ],
        "Empty notes, last in the day": [
            dict(title="Write the changelog", points=13, priority=3,
                 notes="in the readme", sort_order=0, tags=["alpha", "beta"]),
        ],
    }

    source_ids: dict[str, int] = {}
    sub_rows: list[tuple[dict, dict]] = []
    for i, spec in enumerate(roots_spec):
        # Spread the roots over several past days, so planned_date is not the only
        # thing being checked.
        created = client.post("/api/tasks/", json={
            "title": spec["title"], "planned_date": iso(-(1 + i * 3)),
            "points": spec["points"], "priority": spec["priority"],
            "notes": spec["notes"], "sort_order": spec["sort_order"],
        })
        assert created.status_code == status.HTTP_201_CREATED, created.text
        source_ids[spec["title"]] = created.json()["id"]

        for sub_spec in subs_spec.get(spec["title"], []):
            # No planned_date: the subtask inherits its parent's past day.
            sub = client.post("/api/tasks/", json={
                "title": sub_spec["title"], "parent_task_id": created.json()["id"],
                "points": sub_spec["points"], "priority": sub_spec["priority"],
                "notes": sub_spec["notes"], "sort_order": sub_spec["sort_order"],
            })
            assert sub.status_code == status.HTTP_201_CREATED, sub.text
            sub_rows.append((sub_spec, sub.json()))

    for spec in roots_spec:
        set_tags(db_session, source_ids[spec["title"]], [tag_ids[n] for n in spec["tags"]])
    for sub_spec, sub_json in sub_rows:
        set_tags(db_session, sub_json["id"], [tag_ids[n] for n in sub_spec["tags"]])
    db_session.commit()

    before = task_rows(db_session)
    tags_before = tag_ids_by_task(db_session)
    every_source = list(source_ids.values()) + [row["id"] for _, row in sub_rows]
    assert len(every_source) == len(set(every_source))

    response = run(client)
    assert response.status_code == status.HTTP_200_OK, response.text
    result = response.json()
    today = date.fromisoformat(result["date"])
    assert today == local_date()
    assert result["tasks_carried"] == len(roots_spec)
    assert result["subtasks_carried"] == len(sub_rows)
    assert result["total_carried"] == result["tasks_carried"] + result["subtasks_carried"]

    after = task_rows(db_session)
    tags_after = tag_ids_by_task(db_session)
    copies = copies_by_source(db_session)

    # One copy per source, and nothing else was written.
    assert set(copies) == set(every_source), "every source must be carried exactly once"
    assert len(after) == len(before) + result["total_carried"]

    for spec in roots_spec:
        source = before[source_ids[spec["title"]]]
        copy = copies[source["id"]]

        assert_fields_equal(copy, source, COPIED_VERBATIM, f"root {spec['title']!r}")
        assert copy["planned_date"] == today, "a copy is planned for today"
        assert copy["status"] == "pending"
        assert copy["carry_count"] == source["carry_count"] + 1
        assert copy["carried_from_id"] == source["id"]
        assert copy["id"] != source["id"]
        assert copy["parent_task_id"] is None
        # Documented non-copies: this is the same unfinished work, not a new
        # occurrence, and it did not happen today.
        assert copy["recurrence_rule"] is None
        assert copy["completed_at"] is None
        assert copy["completed_date"] is None
        assert copy["deleted_at"] is None
        assert copy["miss_reason"] is None
        assert copy["created_at"] >= source["created_at"]
        assert tags_after[copy["id"]] == tags_before[source["id"]]

    for sub_spec, sub_json in sub_rows:
        source = before[sub_json["id"]]
        copy = copies[source["id"]]
        parent_source = before[source["parent_task_id"]]
        parent_copy = copies[parent_source["id"]]

        assert_fields_equal(copy, source, COPIED_VERBATIM, f"subtask {sub_spec['title']!r}")
        assert copy["planned_date"] == today
        assert copy["status"] == "pending"
        assert copy["carry_count"] == source["carry_count"] + 1
        assert copy["carried_from_id"] == source["id"]
        assert copy["id"] != source["id"]
        assert copy["recurrence_rule"] is None
        assert copy["created_at"] >= source["created_at"]
        # The copy hangs under the *copy* of its parent, never under the original.
        assert copy["parent_task_id"] == parent_copy["id"]
        assert copy["parent_task_id"] != parent_source["id"]
        assert parent_copy["id"] != parent_source["id"]
        assert tags_after[copy["id"]] == tags_before[source["id"]]

    # Sources become "missed" and stay otherwise identical, tags included.
    for source_id in every_source:
        assert after[source_id]["status"] == "missed", f"source {source_id} not missed"
        assert_fields_equal(after[source_id], before[source_id],
                            SOURCE_UNCHANGED, f"source {source_id}")
        assert tags_after[source_id] == tags_before[source_id]


# ---------------------------------------------------------------------------
# 2/3. A backlog larger than the 400-id slice boundary
# ---------------------------------------------------------------------------

# Carry-over slices its set-based reads and writes at 400 ids to stay inside
# SQLite's bound-parameter cap (app/routers/carry_over.py: _SLICE), so a backlog
# below 400 would never exercise the second slice.
LARGE_BACKLOG_ROOTS = 450
LARGE_BACKLOG_SLICE = 400

# A backlog this size must still cost a fixed handful of statements. Measured: 11
# for the 750 sources below -- overdue read + 2 selectin loads (subtasks, tags, for
# roots and subtasks) + 2 sliced copy reads + 2 batched inserts + 1 tag insert +
# 2 sliced updates. The bound adds four statements of margin, and still sits below
# what one query per source would cost by two orders of magnitude.
LARGE_BACKLOG_MAX_STATEMENTS = 15


class Backlog(NamedTuple):
    root_ids: list[int]
    subtask_ids: list[int]
    subtask_parents: dict[int, int]
    tagged: dict[int, list[int]]

    @property
    def source_ids(self) -> list[int]:
        return self.root_ids + self.subtask_ids

    @property
    def total(self) -> int:
        return len(self.root_ids) + len(self.subtask_ids)


def seed_backlog(
    db_session,
    roots: int = LARGE_BACKLOG_ROOTS,
    subs_per_third_root: int = 2,
) -> Backlog:
    """An overdue backlog with subtasks and tags, seeded in a handful of statements.

    Built with bulk inserts rather than the API so the fixture does not cost
    thousands of round-trips; the carry-over run under test still goes through
    HTTP.
    """
    tag_ids = [
        tag_id
        for (tag_id,) in db_session.execute(select(Tag.id).order_by(Tag.name)).all()
    ]
    planned, original = local_date() - timedelta(days=2), local_date() - timedelta(days=9)
    created = utcnow()

    root_rows = [
        dict(
            title=f"Backlog {i}", notes=None if i % 3 == 0 else f"note {i}",
            points=i % 101, priority=i % 4, sort_order=i, planned_date=planned,
            original_date=original, status="pending", carry_count=i % 3,
            created_at=created,
        )
        for i in range(roots)
    ]
    root_ids = list(
        db_session.execute(insert(Task.__table__).returning(Task.__table__.c.id), root_rows)
        .scalars()
        .all()
    )

    sub_rows = []
    for i in range(0, roots, 3):
        for s in range(subs_per_third_root):
            sub_rows.append(dict(
                title=f"Backlog {i} step {s}", notes=f"sub note {i}-{s}",
                points=s * 3, priority=s % 4, sort_order=s,
                parent_task_id=root_ids[i], planned_date=planned,
                original_date=original, status="pending", carry_count=0,
                created_at=created,
            ))
    sub_ids = list(
        db_session.execute(insert(Task.__table__).returning(Task.__table__.c.id), sub_rows)
        .scalars()
        .all()
    )
    subtask_parents = {
        sub_id: row["parent_task_id"] for sub_id, row in zip(sub_ids, sub_rows)
    }

    tagged: dict[int, list[int]] = {}
    links = []
    for i, root_id in enumerate(root_ids):
        if i % 2 == 0:
            tagged[root_id] = [tag_ids[i % len(tag_ids)]]
            links.append(dict(task_id=root_id, tag_id=tag_ids[i % len(tag_ids)]))
    for j, sub_id in enumerate(sub_ids):
        if j % 5 == 0:
            tagged[sub_id] = [tag_ids[j % len(tag_ids)]]
            links.append(dict(task_id=sub_id, tag_id=tag_ids[j % len(tag_ids)]))
    if links:
        db_session.execute(insert(TaskTag.__table__), links)
    db_session.commit()

    return Backlog(
        root_ids=root_ids,
        subtask_ids=sub_ids,
        subtask_parents=subtask_parents,
        tagged=tagged,
    )


def test_large_backlog_is_carried_in_full_within_a_constant_statement_count(client, db_session):
    """More roots than the 400-id slice, so the sliced reads and writes must hold up.

    Checks the copies are complete and correctly wired, that no source is left
    pending, and that the statement count stays flat now that the reads and writes
    are sliced rather than repeated per row.
    """
    db_session.add_all([Tag(name="work"), Tag(name="home")])
    db_session.commit()
    backlog = seed_backlog(db_session)
    assert len(backlog.source_ids) > LARGE_BACKLOG_SLICE, "the slice boundary must be crossed"

    with count_statements(db_session.get_bind()) as statements:
        response = run(client)

    assert response.status_code == status.HTTP_200_OK, response.text
    result = response.json()
    assert result["tasks_carried"] == len(backlog.root_ids)
    assert result["subtasks_carried"] == len(backlog.subtask_ids)
    assert result["total_carried"] == backlog.total

    rows = task_rows(db_session)
    copies = copies_by_source(db_session)
    assert set(copies) == set(backlog.source_ids), "every source must be carried exactly once"
    assert len(rows) == len(backlog.source_ids) + backlog.total

    tags_after = tag_ids_by_task(db_session)
    for sub_id, parent_source_id in backlog.subtask_parents.items():
        parent_copy = copies[parent_source_id]
        assert copies[sub_id]["parent_task_id"] == parent_copy["id"]
    for task_id, expected in backlog.tagged.items():
        copy = copies[task_id]
        assert tags_after[copy["id"]] == expected == tags_after[task_id]

    # No overdue root is left pending anywhere.
    assert all(rows[source_id]["status"] == "missed" for source_id in backlog.source_ids)
    still_overdue = db_session.execute(
        select(func.count())
        .select_from(Task.__table__)
        .where(
            Task.__table__.c.status == "pending",
            Task.__table__.c.parent_task_id.is_(None),
            Task.__table__.c.planned_date < date.fromisoformat(result["date"]),
        )
    ).scalar_one()
    assert still_overdue == 0

    assert len(statements) <= LARGE_BACKLOG_MAX_STATEMENTS, (
        f"{len(statements)} statements for {backlog.total} copies:\n"
        + "\n".join(f"  {s.splitlines()[0][:90]}" for s in statements)
    )


def test_second_carry_over_over_a_large_backlog_creates_and_changes_nothing(client, db_session):
    """Idempotency has to survive the bulk path, not just the small one."""
    db_session.add_all([Tag(name="work"), Tag(name="home")])
    db_session.commit()
    backlog = seed_backlog(db_session)

    first = run(client)
    assert first.status_code == status.HTTP_200_OK, first.text
    assert first.json()["total_carried"] == backlog.total

    before = task_rows(db_session)
    before_tags = tag_ids_by_task(db_session)

    second = run(client)
    assert second.status_code == status.HTTP_200_OK, second.text
    assert second.json()["date"] == first.json()["date"]
    assert second.json()["tasks_carried"] == 0
    assert second.json()["subtasks_carried"] == 0
    assert second.json()["total_carried"] == 0

    assert task_rows(db_session) == before, "the second run must change no column"
    assert tag_ids_by_task(db_session) == before_tags, "the second run must add no tag links"
    assert set(copies_by_source(db_session)) == set(backlog.source_ids)


# ---------------------------------------------------------------------------
# 4. The unique carried_from_id conflict, for real
# ---------------------------------------------------------------------------


def test_conflict_on_carried_from_id_is_retried_without_duplicates(monkeypatch):
    """A concurrent writer winning the race must cost a retry, not a 500.

    The race is the real one: carry-over reads which sources already have a copy,
    then writes the whole batch in a single statement, so a copy that appears in
    between becomes a unique-index violation. The competing copy is committed here,
    before the request, and the first read is hooked to miss it -- exactly what the
    endpoint would have seen had the competitor committed a moment after that read.
    It survives the rollback the retry performs, so the retry finds a copy already
    there and must carry the rest without duplicating it.

    This test brings its own session rather than the shared `client`/`db_session`
    fixtures, because the endpoint calls `session.rollback()` on its way into the
    retry. Against the fixture that rollback unwinds the fixture's still-uncommitted
    transaction and deletes the rows the test just created; a session that commits
    for real keeps the rollback scoped to the batch that failed, as in production.

    TestClient re-raises unhandled server errors, so a broken retry fails this test
    by raising IntegrityError instead of by asserting on a 500.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.db import get_db
    from app.main import app
    from app.models import Base
    from app.routers import carry_over

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    try:
        db.add(Tag(name="work"))
        db.commit()

        loser = client.post(
            "/api/tasks/", json={"title": "Loser of the race", "planned_date": iso(-1),
                                 "points": 11, "notes": "note", "sort_order": 1}
        ).json()
        winner = client.post(
            "/api/tasks/", json={"title": "Winner of the retry", "planned_date": iso(-2),
                                 "points": 22, "priority": 2, "sort_order": 2}
        ).json()
        winner_sub = client.post(
            "/api/tasks/", json={"title": "Sub of the winner",
                                 "parent_task_id": winner["id"], "points": 3}
        ).json()
        set_tags(db, loser["id"], [db.execute(select(Tag.id)).scalar_one()])
        set_tags(db, winner["id"], [db.execute(select(Tag.id)).scalar_one()])
        db.commit()

        # The concurrent writer, committed before the run and untouched by its rollback.
        raced_id = loser["id"]
        db.add(Task(title="Concurrent copy", status="pending",
                    planned_date=local_date(), carried_from_id=raced_id))
        db.commit()

        reads: list[list[int]] = []
        real_read = carry_over._copied_source_ids

        def read_missing_the_race(db, source_ids):
            """The first read misses the competing copy; the retry's read does not."""
            copies = real_read(db, source_ids)
            reads.append(sorted(source_ids))
            if len(reads) == 1:
                copies.discard(raced_id)
            return copies

        monkeypatch.setattr(carry_over, "_copied_source_ids", read_missing_the_race)

        response = run(client)
        assert response.status_code == status.HTTP_200_OK, response.text
        assert len(reads) == 2, (
            "the conflict should have forced exactly one retry that re-read the sources"
        )

        result = response.json()
        assert result["tasks_carried"] == 1, "only the task that did not lose the race is carried"
        assert result["subtasks_carried"] == 1
        assert result["total_carried"] == 2

        rows = task_rows(db)
        copies = copies_by_source(db)
        assert set(copies) == {raced_id, winner["id"], winner_sub["id"]}
        assert copies[raced_id]["title"] == "Concurrent copy", "the winner keeps its row"
        assert rows[raced_id]["status"] == "missed"
        assert rows[winner["id"]]["status"] == "missed"
        assert rows[winner_sub["id"]]["status"] == "missed"

        winner_copy = copies[winner["id"]]
        assert winner_copy["title"] == "Winner of the retry"
        assert winner_copy["planned_date"] == date.fromisoformat(result["date"])
        assert winner_copy["status"] == "pending"
        assert winner_copy["carry_count"] == rows[winner["id"]]["carry_count"] + 1
        assert copies[winner_sub["id"]]["parent_task_id"] == winner_copy["id"]
        # The retry carried the winner's tags, and left the competitor's row
        # untouched: a row carry-over never wrote carries no tags of its own.
        tags = tag_ids_by_task(db)
        only_tag = db.execute(select(Tag.id)).scalar_one()
        assert tags[raced_id] == tags[winner["id"]] == [only_tag]
        assert tags[winner_copy["id"]] == [only_tag]
        assert tags[copies[raced_id]["id"]] == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()
