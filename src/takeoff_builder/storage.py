from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass
class SupabaseConfig:
    url: str
    api_key: str
    table: str = "review_records"


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _supabase_config() -> SupabaseConfig | None:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    api_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    )
    table = os.environ.get("SUPABASE_REVIEWS_TABLE", "review_records").strip() or "review_records"
    if not url or not api_key:
        return None
    return SupabaseConfig(url=url, api_key=api_key, table=table)


def get_storage_backend(db_path: Path) -> dict[str, str]:
    config = _supabase_config()
    if config:
        return {
            "type": "supabase",
            "label": "Supabase",
            "target": f"{config.url}/rest/v1/{config.table}",
        }
    return {
        "type": "sqlite",
        "label": "SQLite",
        "target": str(db_path),
    }


def init_review_db(db_path: Path) -> None:
    if _supabase_config():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS review_records (
                takeoff_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                reviewer TEXT,
                notes TEXT,
                corrected_items_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def get_review_record(db_path: Path, takeoff_id: str) -> dict[str, Any]:
    config = _supabase_config()
    if config:
        return _get_review_record_supabase(config, takeoff_id)

    init_review_db(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT takeoff_id, status, reviewer, notes, corrected_items_json, updated_at FROM review_records WHERE takeoff_id = ?",
            (takeoff_id,),
        ).fetchone()
    if not row:
        return _default_review_record(takeoff_id)
    return {
        "takeoff_id": row["takeoff_id"],
        "status": row["status"],
        "reviewer": row["reviewer"] or "",
        "notes": row["notes"] or "",
        "corrected_items": json.loads(row["corrected_items_json"]),
        "updated_at": row["updated_at"],
    }


def save_review_record(db_path: Path, takeoff_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = {
        "takeoff_id": takeoff_id,
        "status": str(payload.get("status") or "in_review"),
        "reviewer": str(payload.get("reviewer") or ""),
        "notes": str(payload.get("notes") or ""),
        "corrected_items": payload.get("corrected_items") or [],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    config = _supabase_config()
    if config:
        return _save_review_record_supabase(config, record)

    init_review_db(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO review_records (takeoff_id, status, reviewer, notes, corrected_items_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(takeoff_id) DO UPDATE SET
                status = excluded.status,
                reviewer = excluded.reviewer,
                notes = excluded.notes,
                corrected_items_json = excluded.corrected_items_json,
                updated_at = excluded.updated_at
            """,
            (
                record["takeoff_id"],
                record["status"],
                record["reviewer"],
                record["notes"],
                json.dumps(record["corrected_items"]),
                record["updated_at"],
            ),
        )
    return record


def _default_review_record(takeoff_id: str) -> dict[str, Any]:
    return {
        "takeoff_id": takeoff_id,
        "status": "not_started",
        "reviewer": "",
        "notes": "",
        "corrected_items": [],
        "updated_at": None,
    }


def _get_review_record_supabase(config: SupabaseConfig, takeoff_id: str) -> dict[str, Any]:
    path = f"/rest/v1/{config.table}?takeoff_id=eq.{quote(takeoff_id)}&select=takeoff_id,status,reviewer,notes,corrected_items,updated_at"
    try:
        rows = _supabase_request(config, path, method="GET")
    except HTTPError as error:
        raise RuntimeError(_read_error_body(error)) from error
    if not rows:
        return _default_review_record(takeoff_id)
    row = rows[0]
    return {
        "takeoff_id": row["takeoff_id"],
        "status": row.get("status") or "not_started",
        "reviewer": row.get("reviewer") or "",
        "notes": row.get("notes") or "",
        "corrected_items": row.get("corrected_items") or [],
        "updated_at": row.get("updated_at"),
    }


def _save_review_record_supabase(config: SupabaseConfig, record: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "takeoff_id": record["takeoff_id"],
        "status": record["status"],
        "reviewer": record["reviewer"],
        "notes": record["notes"],
        "corrected_items": record["corrected_items"],
    }
    headers = {
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    try:
        rows = _supabase_request(config, f"/rest/v1/{config.table}", method="POST", payload=[payload], extra_headers=headers)
    except HTTPError as error:
        raise RuntimeError(_read_error_body(error)) from error
    if not rows:
        return record
    row = rows[0]
    return {
        "takeoff_id": row["takeoff_id"],
        "status": row.get("status") or record["status"],
        "reviewer": row.get("reviewer") or "",
        "notes": row.get("notes") or "",
        "corrected_items": row.get("corrected_items") or [],
        "updated_at": row.get("updated_at") or record["updated_at"],
    }


def _supabase_request(
    config: SupabaseConfig,
    path: str,
    method: str,
    payload: Any | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    headers = {
        "apikey": config.api_key,
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(f"{config.url}{path}", data=body, headers=headers, method=method)
    with urlopen(request, timeout=15) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else None


def _read_error_body(error: HTTPError) -> str:
    try:
        payload = error.read().decode("utf-8")
    except Exception:
        payload = ""
    return payload or f"{error.code} {error.reason}"
