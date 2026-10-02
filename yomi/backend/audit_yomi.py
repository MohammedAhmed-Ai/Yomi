from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, get_db
from app import models  # noqa: F401
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
D = "2026-10-02"


def days_count():
    with engine.connect() as c:
        return c.exec_driver_sql("select count(*) from days").scalar()


def row(task_id):
    with engine.connect() as c:
        return c.exec_driver_sql("select status, deleted_at from tasks where id=?", (task_id,)).fetchone()


def make(title="T", date=D, **extra):
    r = client.post("/api/tasks", json={"title": title, "planned_date": date, **extra})
    return r, (r.json() if r.status_code < 300 else {})


def day_tasks(date=D):
    body = client.get(f"/api/days/{date}").json()
    return body.get("tasks", []) if isinstance(body, dict) else []


def a():
    r = client.get("/api/health")
    return r.status_code == 200 and r.json() == {"status": "ok"}, r.text


def b():
    r, t = make("T1")
    found = any(x.get("id") == t.get("id") for x in day_tasks())
    return r.status_code in (200, 201) and found, f"create={r.status_code} in_day={found}"


def c():
    r = client.get("/api/days/not-a-date")
    return r.status_code == 400, f"status={r.status_code}"


def d():
    _, t = make("T-complete")
    i = t["id"]
    r1 = client.post(f"/api/tasks/{i}/complete").json()
    r2 = client.post(f"/api/tasks/{i}/complete")
    r3 = client.post(f"/api/tasks/{i}/uncomplete").json()
    ok = (r1.get("status") == "done" and r1.get("completed_at") and r1.get("completed_date")
          and r2.status_code == 200 and r3.get("status") == "pending"
          and r3.get("completed_at") is None and r3.get("completed_date") is None)
    return bool(ok), f"done={r1.get('status')} again={r2.status_code} undone={r3.get('status')}"


def e():
    _, p = make("Parent")
    r, s = make("Sub", "2026-10-09", parent_task_id=p["id"])
    parent = next((x for x in day_tasks() if x.get("id") == p["id"]), {})
    nested = any(x.get("id") == s.get("id") for x in parent.get("subtasks", []))
    return r.status_code in (200, 201) and s.get("planned_date") == D and nested, \
        f"create={r.status_code} inherits_date={s.get('planned_date')} nested={nested}"


def f():
    _, p = make("P2")
    _, s = make("S2", parent_task_id=p["id"])
    r, _ = make("S-of-S", parent_task_id=s["id"])
    return 400 <= r.status_code < 500, f"status={r.status_code} (must be rejected)"


def g():
    _, t = make("Old", points=10)
    r = client.patch(f"/api/tasks/{t['id']}", json={"title": "New", "points": 25})
    j = r.json() if r.status_code < 300 else {}
    return r.status_code == 200 and j.get("title") == "New" and j.get("points") == 25, f"status={r.status_code}"


def h():
    _, p = make("DelParent")
    _, s = make("DelSub", parent_task_id=p["id"])
    r = client.delete(f"/api/tasks/{p['id']}")
    ids = [x.get("id") for x in day_tasks()]
    hidden = p["id"] not in ids and s["id"] not in ids
    rp, rs = row(p["id"]), row(s["id"])
    soft = rp and rs and rp[0] == "deleted" and rp[1] and rs[0] == "deleted" and rs[1]
    return r.status_code in (200, 204) and hidden and bool(soft), f"status={r.status_code} hidden={hidden} rows={rp},{rs}"


def i():
    _, t = make("ToDelete")
    client.delete(f"/api/tasks/{t['id']}")
    r1 = client.patch(f"/api/tasks/{t['id']}", json={"title": "x"})
    r2 = client.post(f"/api/tasks/{t['id']}/complete")
    return r1.status_code == 404 and r2.status_code == 404, f"patch={r1.status_code} complete={r2.status_code}"


def j():
    rs = [client.post("/api/tasks/99999/complete"), client.patch("/api/tasks/99999", json={"title": "x"}),
          client.delete("/api/tasks/99999")]
    codes = [r.status_code for r in rs]
    msgs = [r.json().get("detail") for r in rs]
    return all(c_ == 404 for c_ in codes) and all(msgs), f"codes={codes} msgs={msgs}"


def k():
    r1 = client.post("/api/tags", json={"name": "work"})
    r2 = client.post("/api/tags", json={"name": "work"})
    names = [x.get("name") for x in client.get("/api/tags").json()]
    return r1.status_code in (200, 201) and r2.status_code == 409 and "work" in names, \
        f"first={r1.status_code} duplicate={r2.status_code}"


def l():
    codes = [client.post("/api/tasks", json={"title": "", "planned_date": D}).status_code,
             client.post("/api/tasks", json={"title": "x", "planned_date": D, "points": 5000}).status_code,
             client.post("/api/tasks", json={"title": "x", "planned_date": D, "priority": 9}).status_code]
    return all(c_ in (400, 422) for c_ in codes), f"empty_title/points/priority = {codes}"


def m():
    r, t = make("OrigDate")
    return t.get("original_date") == D, f"original_date={t.get('original_date')} planned_date={t.get('planned_date')}"


def q1():
    _, p = make("Depth0")
    r1, s = make("Depth1", parent_task_id=p["id"])
    r2, _ = make("Depth2", parent_task_id=s.get("id", 0))
    return None, f"level1={r1.status_code} level2={r2.status_code} (level2 must be 4xx)"


def q2():
    before = days_count()
    _, t = make("DaysCheck", "2026-11-01")
    after_create = days_count()
    client.post(f"/api/tasks/{t['id']}/complete")
    after_complete = days_count()
    client.get("/api/days/2026-11-01")
    after_get = days_count()
    ok = before == after_create == after_complete == 0 and after_get == 1
    return ok, f"counts: before={before} create={after_create} complete={after_complete} GET={after_get} (expected 0,0,0,1)"


print("--- Yomi audit ---")
for name, fn in [("a health", a), ("b create+day", b), ("c bad date", c), ("d complete/uncomplete", d),
                 ("e subtask", e), ("f subtask of subtask", f), ("g patch", g), ("h soft delete", h),
                 ("i deleted->404", i), ("j unknown id", j), ("k tags", k), ("l validation", l),
                 ("m original_date", m), ("Q1 depth", q1), ("Q2 days rows", q2)]:
    try:
        ok, info = fn()
        label = "INFO" if ok is None else ("PASS" if ok else "FAIL")
    except Exception as ex:
        label, info = "ERROR", repr(ex)
    print(f"{name}: {label} | {info}")
print("day response keys:", sorted(client.get(f"/api/days/{D}").json().keys()))
print("routes:", sorted({(m_, r.path) for r in app.routes for m_ in getattr(r, "methods", []) if r.path.startswith("/api")}))