"""Local Study Studio API and static file server (Python standard library only)."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "study_library.sqlite3"
HTML_PATH = ROOT / "study_workflow.html"
MAX_BODY_BYTES = 10 * 1024 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with db_connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS studies (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                pack_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id TEXT PRIMARY KEY,
                study_id TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
                attempt_number INTEGER NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                reflection TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS quiz_attempts_study_date "
            "ON quiz_attempts(study_id, created_at DESC)"
        )


def record_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"],
        "sourceName": row["source_name"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "pack": json.loads(row["pack_json"]),
    }


def attempt_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "studyId": row["study_id"],
        "attemptNumber": row["attempt_number"],
        "score": row["score"],
        "total": row["total"],
        "percentage": round((row["score"] / row["total"]) * 100) if row["total"] else 0,
        "result": json.loads(row["result_json"]),
        "reflection": row["reflection"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


class StudyStudioHandler(BaseHTTPRequestHandler):
    server_version = "StudyStudio/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json(status, {"error": message})

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("Request body is empty or too large.")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    def study_values(self, body: dict) -> tuple[str, str, str, str]:
        pack = body.get("pack")
        if not isinstance(pack, dict):
            raise ValueError("A study pack object is required.")
        title = str(body.get("title") or pack.get("title") or "Untitled study pack").strip()
        summary = str(pack.get("summary") or "").strip()
        source_name = str(body.get("sourceName") or "").strip()
        if not title:
            title = "Untitled study pack"
        return title[:200], summary[:4000], source_name[:500], json.dumps(pack, ensure_ascii=False)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/" or path == "/study_workflow.html":
            try:
                body = HTML_PATH.read_bytes()
            except OSError:
                self.send_error(404, "Study Studio page not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/health":
            self.send_json(200, {"ok": True, "storage": "sqlite"})
            return

        if path == "/api/studies":
            with db_connect() as db:
                rows = db.execute(
                    "SELECT * FROM studies ORDER BY updated_at DESC, created_at DESC"
                ).fetchall()
            self.send_json(200, [record_to_dict(row) for row in rows])
            return

        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "studies"] and parts[3] == "attempts":
            study_id = parts[2]
            with db_connect() as db:
                exists = db.execute("SELECT 1 FROM studies WHERE id = ?", (study_id,)).fetchone()
                rows = db.execute(
                    "SELECT * FROM quiz_attempts WHERE study_id = ? ORDER BY attempt_number DESC",
                    (study_id,),
                ).fetchall()
            if exists is None:
                self.send_error_json(404, "Study material not found.")
            else:
                self.send_json(200, [attempt_to_dict(row) for row in rows])
            return

        if len(parts) == 3 and parts[:2] == ["api", "attempts"]:
            with db_connect() as db:
                row = db.execute("SELECT * FROM quiz_attempts WHERE id = ?", (parts[2],)).fetchone()
            if row is None:
                self.send_error_json(404, "Quiz attempt not found.")
            else:
                self.send_json(200, attempt_to_dict(row))
            return

        if path.startswith("/api/studies/"):
            study_id = path.rsplit("/", 1)[-1]
            with db_connect() as db:
                row = db.execute("SELECT * FROM studies WHERE id = ?", (study_id,)).fetchone()
            if row is None:
                self.send_error_json(404, "Study material not found.")
            else:
                self.send_json(200, record_to_dict(row))
            return

        self.send_error_json(404, "Route not found.")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "studies"] and parts[3] == "attempts":
            study_id = parts[2]
            try:
                body = self.read_json()
                attempt = body.get("attempt")
                if not isinstance(attempt, dict):
                    raise ValueError("A quiz attempt object is required.")
                score = int(attempt.get("score", -1))
                total = int(attempt.get("total", 0))
                if total < 1 or score < 0 or score > total:
                    raise ValueError("Quiz score must be between zero and the number of questions.")
                result_json = json.dumps(attempt, ensure_ascii=False)
            except (ValueError, TypeError) as exc:
                self.send_error_json(400, str(exc))
                return

            attempt_id = str(uuid.uuid4())
            timestamp = now_iso()
            with db_connect() as db:
                exists = db.execute("SELECT 1 FROM studies WHERE id = ?", (study_id,)).fetchone()
                if exists is None:
                    self.send_error_json(404, "Study material not found.")
                    return
                row_number = db.execute(
                    "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM quiz_attempts WHERE study_id = ?",
                    (study_id,),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO quiz_attempts "
                    "(id, study_id, attempt_number, score, total, result_json, reflection, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, '', ?, ?)",
                    (attempt_id, study_id, row_number, score, total, result_json, timestamp, timestamp),
                )
                row = db.execute("SELECT * FROM quiz_attempts WHERE id = ?", (attempt_id,)).fetchone()
            self.send_json(201, attempt_to_dict(row))
            return

        if path != "/api/studies":
            self.send_error_json(404, "Route not found.")
            return
        try:
            body = self.read_json()
            title, summary, source_name, pack_json = self.study_values(body)
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return

        study_id = str(uuid.uuid4())
        timestamp = now_iso()
        with db_connect() as db:
            db.execute(
                "INSERT INTO studies (id, title, summary, source_name, pack_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (study_id, title, summary, source_name, pack_json, timestamp, timestamp),
            )
            row = db.execute("SELECT * FROM studies WHERE id = ?", (study_id,)).fetchone()
        self.send_json(201, record_to_dict(row))

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/attempts/"):
            attempt_id = path.rsplit("/", 1)[-1]
            try:
                body = self.read_json()
                reflection = str(body.get("reflection") or "").strip()[:4000]
            except ValueError as exc:
                self.send_error_json(400, str(exc))
                return
            with db_connect() as db:
                cursor = db.execute(
                    "UPDATE quiz_attempts SET reflection = ?, updated_at = ? WHERE id = ?",
                    (reflection, now_iso(), attempt_id),
                )
                row = db.execute("SELECT * FROM quiz_attempts WHERE id = ?", (attempt_id,)).fetchone()
            if cursor.rowcount == 0:
                self.send_error_json(404, "Quiz attempt not found.")
            else:
                self.send_json(200, attempt_to_dict(row))
            return

        if not path.startswith("/api/studies/"):
            self.send_error_json(404, "Route not found.")
            return
        study_id = path.rsplit("/", 1)[-1]
        try:
            body = self.read_json()
            title, summary, source_name, pack_json = self.study_values(body)
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return

        with db_connect() as db:
            existing = db.execute("SELECT * FROM studies WHERE id = ?", (study_id,)).fetchone()
            if existing is None:
                self.send_error_json(404, "Study material not found.")
                return
            timestamp = now_iso()
            db.execute(
                "UPDATE studies SET title = ?, summary = ?, source_name = ?, pack_json = ?, updated_at = ? "
                "WHERE id = ?",
                (title, summary, source_name or existing["source_name"], pack_json, timestamp, study_id),
            )
            row = db.execute("SELECT * FROM studies WHERE id = ?", (study_id,)).fetchone()
        self.send_json(200, record_to_dict(row))

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/attempts/"):
            attempt_id = path.rsplit("/", 1)[-1]
            with db_connect() as db:
                cursor = db.execute("DELETE FROM quiz_attempts WHERE id = ?", (attempt_id,))
            if cursor.rowcount == 0:
                self.send_error_json(404, "Quiz attempt not found.")
                return
            self.send_response(204)
            self.end_headers()
            return

        if not path.startswith("/api/studies/"):
            self.send_error_json(404, "Route not found.")
            return
        study_id = path.rsplit("/", 1)[-1]
        with db_connect() as db:
            cursor = db.execute("DELETE FROM studies WHERE id = ?", (study_id,))
        if cursor.rowcount == 0:
            self.send_error_json(404, "Study material not found.")
            return
        self.send_response(204)
        self.end_headers()


def main() -> None:
    initialize_database()
    port = int(os.environ.get("STUDY_STUDIO_PORT", "8001"))
    server = ThreadingHTTPServer(("127.0.0.1", port), StudyStudioHandler)
    print(f"Study Studio is running at http://127.0.0.1:{port}")
    print(f"SQLite library: {DB_PATH.name}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Study Studio.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
