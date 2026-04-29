from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import get_connection, init_db, seed_db
from .schemas import (
    ReportCreate,
    ReportRead,
    SpotCreate,
    SpotRead,
    SpotUpdateStatus,
    SubscriptionCreate,
    SubscriptionRead,
    UserCreate,
    UserRead,
)


app = FastAPI(
    title="Parking MVP API",
    version="0.1.0",
    description="Минимальный backend для MVP сервиса поиска парковки.",
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_db()


def rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def fmt_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def get_dashboard_stats(conn: Any) -> dict[str, int]:
    return {
        "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "active_spots": conn.execute(
            """
            SELECT COUNT(*) FROM parking_spots
            WHERE status = 'free' AND expires_at > datetime('now')
            """
        ).fetchone()[0],
        "active_subscriptions": conn.execute(
            """
            SELECT COUNT(*) FROM subscriptions
            WHERE status = 'active' AND ends_at > datetime('now')
            """
        ).fetchone()[0],
        "open_reports": conn.execute(
            "SELECT COUNT(*) FROM reports WHERE status = 'open'"
        ).fetchone()[0],
    }


def expire_stale_spots(conn: Any) -> None:
    conn.execute(
        """
        UPDATE parking_spots
        SET status = 'expired'
        WHERE status = 'free' AND expires_at <= datetime('now')
        """
    )
    conn.commit()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request) -> HTMLResponse:
    conn = get_connection()
    expire_stale_spots(conn)
    stats = get_dashboard_stats(conn)
    users = rows_to_dicts(conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall())
    spots = rows_to_dicts(
        conn.execute(
            """
            SELECT s.*, u.name AS user_name
            FROM parking_spots s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.created_at DESC
            """
        ).fetchall()
    )
    subscriptions = rows_to_dicts(
        conn.execute(
            """
            SELECT sub.*, u.name AS user_name
            FROM subscriptions sub
            JOIN users u ON u.id = sub.user_id
            ORDER BY sub.created_at DESC
            """
        ).fetchall()
    )
    reports = rows_to_dicts(
        conn.execute(
            """
            SELECT r.*, u.name AS reporter_name, s.address AS spot_address
            FROM reports r
            JOIN users u ON u.id = r.user_id
            JOIN parking_spots s ON s.id = r.spot_id
            ORDER BY r.created_at DESC
            """
        ).fetchall()
    )
    conn.close()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "stats": stats,
            "users": users,
            "spots": spots,
            "subscriptions": subscriptions,
            "reports": reports,
        },
    )


@app.post("/admin/spots/{spot_id}/status")
async def admin_update_spot_status(
    request: Request,
    spot_id: int,
) -> RedirectResponse:
    form_data = parse_qs((await request.body()).decode())
    status = form_data.get("status", [""])[0]
    if status not in {"free", "occupied", "expired", "removed"}:
        raise HTTPException(status_code=400, detail="Unsupported status")

    conn = get_connection()
    existing = conn.execute("SELECT id FROM parking_spots WHERE id = ?", (spot_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Spot not found")

    conn.execute("UPDATE parking_spots SET status = ? WHERE id = ?", (status, spot_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/reports/{report_id}/status")
async def admin_update_report_status(
    request: Request,
    report_id: int,
) -> RedirectResponse:
    form_data = parse_qs((await request.body()).decode())
    status = form_data.get("status", [""])[0]
    spot_status = form_data.get("spot_status", [""])[0]
    if status not in {"open", "reviewed", "resolved", "rejected"}:
        raise HTTPException(status_code=400, detail="Unsupported report status")

    conn = get_connection()
    report = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not report:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")

    conn.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))

    if spot_status:
        if spot_status not in {"free", "occupied", "expired", "removed"}:
            conn.close()
            raise HTTPException(status_code=400, detail="Unsupported spot status")
        conn.execute(
            "UPDATE parking_spots SET status = ? WHERE id = ?",
            (spot_status, report["spot_id"]),
        )

    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/api/users", response_model=UserRead)
def create_user(payload: UserCreate) -> dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (telegram_id, name, role, home_area)
        VALUES (?, ?, 'user', ?)
        """,
        (payload.telegram_id, payload.name, payload.home_area),
    )
    user_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/users", response_model=list[UserRead])
def list_users() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows_to_dicts(rows)


@app.post("/api/spots", response_model=SpotRead)
def create_spot(payload: SpotCreate) -> dict[str, Any]:
    conn = get_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=payload.ttl_minutes)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO parking_spots (
            user_id, area, address, latitude, longitude, status, confidence, expires_at
        )
        VALUES (?, ?, ?, ?, ?, 'free', ?, ?)
        """,
        (
            payload.user_id,
            payload.area,
            payload.address,
            payload.latitude,
            payload.longitude,
            payload.confidence,
            fmt_dt(expires_at),
        ),
    )
    spot_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM parking_spots WHERE id = ?", (spot_id,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/spots", response_model=list[SpotRead])
def list_spots(
    area: str | None = None,
    only_active: bool = Query(default=True),
) -> list[dict[str, Any]]:
    conn = get_connection()
    expire_stale_spots(conn)

    query = "SELECT * FROM parking_spots WHERE 1=1"
    params: list[Any] = []

    if area:
        query += " AND area = ?"
        params.append(area)

    if only_active:
        query += " AND status = 'free' AND expires_at > datetime('now')"

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows_to_dicts(rows)


@app.patch("/api/spots/{spot_id}", response_model=SpotRead)
def update_spot_status(spot_id: int, payload: SpotUpdateStatus) -> dict[str, Any]:
    conn = get_connection()
    existing = conn.execute("SELECT * FROM parking_spots WHERE id = ?", (spot_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Spot not found")

    conn.execute(
        "UPDATE parking_spots SET status = ? WHERE id = ?",
        (payload.status, spot_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM parking_spots WHERE id = ?", (spot_id,)).fetchone()
    conn.close()
    return dict(row)


@app.post("/api/subscriptions", response_model=SubscriptionRead)
def create_subscription(payload: SubscriptionCreate) -> dict[str, Any]:
    conn = get_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    starts_at = datetime.now(timezone.utc)
    ends_at = starts_at + timedelta(days=payload.duration_days)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO subscriptions (user_id, plan, status, starts_at, ends_at, amount_rub)
        VALUES (?, ?, 'active', ?, ?, ?)
        """,
        (
            payload.user_id,
            payload.plan,
            fmt_dt(starts_at),
            fmt_dt(ends_at),
            payload.amount_rub,
        ),
    )
    subscription_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/subscriptions", response_model=list[SubscriptionRead])
def list_subscriptions(user_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    query = "SELECT * FROM subscriptions"
    params: list[Any] = []

    if user_id is not None:
        query += " WHERE user_id = ?"
        params.append(user_id)

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows_to_dicts(rows)


@app.post("/api/reports", response_model=ReportRead)
def create_report(payload: ReportCreate) -> dict[str, Any]:
    conn = get_connection()
    spot = conn.execute("SELECT id FROM parking_spots WHERE id = ?", (payload.spot_id,)).fetchone()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,)).fetchone()
    if not spot or not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Spot or user not found")

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reports (spot_id, user_id, reason, status)
        VALUES (?, ?, ?, 'open')
        """,
        (payload.spot_id, payload.user_id, payload.reason),
    )
    report_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/reports", response_model=list[ReportRead])
def list_reports() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows_to_dicts(rows)


@app.patch("/api/reports/{report_id}", response_model=ReportRead)
def update_report_status(report_id: int, status: str = Query(...)) -> dict[str, Any]:
    if status not in {"open", "reviewed", "resolved", "rejected"}:
        raise HTTPException(status_code=400, detail="Unsupported report status")

    conn = get_connection()
    existing = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")

    conn.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))
    conn.commit()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    return dict(row)
