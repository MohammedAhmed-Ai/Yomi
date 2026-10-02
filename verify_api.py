"""Manual smoke test for the Yomi API.

Runs the full request flow against a throwaway in-memory database so it never
touches the real yomi.db. Run it with:

    py -3.13 verify_api.py

The pytest suite in tests/ is the authoritative check; this script only exists
for a quick end-to-end sanity run.
"""
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import Base, get_db

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=engine)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
D = "2026-10-02"

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'} | {name} {detail}")
    if not condition:
        failures.append(name)


def test_health():
    r = client.get("/api/health")
    check("health", r.status_code == 200 and r.json() == {"status": "ok"}, r.text)


def test_tags_flow():
    r = client.post("/api/tags/", json={"name": "TestTag"})
    check("create tag -> 201", r.status_code == 201, f"got {r.status_code}")
    tag_id = r.json()["id"]

    dup = client.post("/api/tags/", json={"name": "TestTag"})
    check("duplicate tag -> 409", dup.status_code == 409, f"got {dup.status_code}")

    listed = client.get("/api/tags/")
    check("list tags", any(t["id"] == tag_id for t in listed.json()), listed.text)


def test_days_flow():
    r = client.get(f"/api/days/{D}")
    check("get day auto-creates", r.status_code == 200 and r.json()["date"] == D, r.text)

    bad = client.get("/api/days/not-a-date")
    check("bad date -> 400", bad.status_code == 400, f"got {bad.status_code}")


def test_tasks_flow():
    parent = client.post("/api/tasks/", json={"title": "Parent", "planned_date": D}).json()
    check("create task -> 201", parent.get("original_date") == D, str(parent))

    sub = client.post("/api/tasks/", json={"title": "Sub", "parent_task_id": parent["id"]}).json()
    check("subtask inherits date", sub.get("planned_date") == D, str(sub))

    deep = client.post("/api/tasks/", json={"title": "Deep", "parent_task_id": sub["id"]})
    check("subtask of subtask -> 400", deep.status_code == 400, f"got {deep.status_code}")

    done = client.post(f"/api/tasks/{parent['id']}/complete").json()
    check("complete", done.get("status") == "done" and done.get("completed_date"), str(done))

    undone = client.post(f"/api/tasks/{parent['id']}/uncomplete").json()
    check("uncomplete", undone.get("status") == "pending" and undone.get("completed_at") is None, str(undone))

    deleted = client.delete(f"/api/tasks/{parent['id']}")
    check("delete -> 204", deleted.status_code == 204, f"got {deleted.status_code}")

    gone = client.patch(f"/api/tasks/{parent['id']}", json={"title": "x"})
    check("patch deleted -> 404", gone.status_code == 404, f"got {gone.status_code}")

    ids = [t["id"] for t in client.get(f"/api/days/{D}").json()["tasks"]]
    check("deleted parent+subtask hidden from day", parent["id"] not in ids and sub["id"] not in ids, str(ids))


def test_validation():
    codes = [
        client.post("/api/tasks/", json={"title": "", "planned_date": D}).status_code,
        client.post("/api/tasks/", json={"title": "x", "planned_date": D, "points": 5000}).status_code,
        client.post("/api/tasks/", json={"title": "x", "planned_date": D, "priority": 9}).status_code,
        client.post("/api/tasks/", json={"title": "x", "status": "done"}).status_code,
    ]
    check("validation errors -> 422", all(c == 422 for c in codes), str(codes))


if __name__ == "__main__":
    try:
        test_health()
        test_tags_flow()
        test_days_flow()
        test_tasks_flow()
        test_validation()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if failures:
        print(f"\n{len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    print("\nAPI verification successful: all checks passed.")