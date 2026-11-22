"""The desk's own store (D-18, D-20, D-21): one SQLite file with the outbox, the synthetic calendar, the escalation
queue and the processed intakes (for duplicate detection).

The outbox is the only sink in the package. A row's status is always one of `logged_not_sent`, `blocked_consent`,
`blocked_brand` or `suppressed_duplicate`; there is no "sent" status and no code that could send.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from intake_desk.models import OutboundRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS intakes (
    intake_id TEXT PRIMARY KEY,
    contact_id TEXT,
    received_at TEXT NOT NULL,
    route TEXT NOT NULL,
    outcome TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    outbound_id TEXT PRIMARY KEY,
    intake_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT NOT NULL,
    template TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('logged_not_sent','blocked_consent','blocked_brand','suppressed_duplicate')),
    detail TEXT NOT NULL,
    logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    booking_id TEXT PRIMARY KEY,
    intake_id TEXT NOT NULL,
    contact_id TEXT,
    slot_start TEXT NOT NULL UNIQUE,
    calendar TEXT NOT NULL CHECK (calendar = 'synthetic'),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS queue (
    queue_id TEXT PRIMARY KEY,
    intake_id TEXT NOT NULL,
    contact_id TEXT,
    proposed_action TEXT NOT NULL,
    why TEXT NOT NULL,
    reasons TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected')),
    decided_action TEXT,
    decided_note TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class QueueError(LookupError):
    """Unknown queue item, or one already decided."""


class Store:
    def __init__(self, path: str | Path = ":memory:", jsonl: Path | None = None) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.jsonl = jsonl

    def close(self) -> None:
        self.conn.close()

    # -- outbox (the only sink) -------------------------------------------------

    def log_outbound(self, rec: OutboundRecord) -> OutboundRecord:
        with self.conn:
            self.conn.execute(
                "INSERT INTO outbox (outbound_id, intake_id, kind, channel, recipient, template, body, status, detail, logged_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rec.outbound_id, rec.intake_id, rec.kind, rec.channel, rec.to, rec.template, rec.body, rec.status, rec.detail, rec.logged_at))
        if self.jsonl is not None:
            self.jsonl.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl.open("a", encoding="utf-8") as f:
                f.write(rec.model_dump_json() + "\n")
        return rec

    def outbox(self, intake_id: str | None = None) -> list[OutboundRecord]:
        sql, args = "SELECT * FROM outbox", tuple[str, ...]()
        if intake_id:
            sql, args = sql + " WHERE intake_id = ?", (intake_id,)
        rows = self.conn.execute(sql + " ORDER BY logged_at, outbound_id", args).fetchall()
        return [OutboundRecord(outbound_id=r["outbound_id"], intake_id=r["intake_id"], kind=r["kind"], channel=r["channel"], to=r["recipient"],
                               template=r["template"], body=r["body"], status=r["status"], detail=r["detail"], logged_at=r["logged_at"]) for r in rows]

    # -- intakes (duplicates, D-15) ------------------------------------------

    def find_duplicate(self, intake_id: str, contact_id: str | None, received_at: datetime, window_hours: int) -> dict[str, Any] | None:
        if contact_id is None:
            return None
        lo = (received_at - timedelta(hours=window_hours)).astimezone(UTC).isoformat()
        hi = received_at.astimezone(UTC).isoformat()
        row = self.conn.execute(
            "SELECT * FROM intakes WHERE contact_id = ? AND intake_id != ? AND received_at >= ? AND received_at <= ? ORDER BY received_at LIMIT 1",
            (contact_id, intake_id, lo, hi)).fetchone()
        return dict(row) if row else None

    def prior_action(self, intake_id: str, contact_id: str | None, received_at: datetime, window_hours: int, route: str) -> str | None:
        """The intake whose action already covers a new `route` for this caller inside the window (D-15), or None.

        Decided from state, not from the earliest intake: an earlier intake with the same route, or for `book` any
        booking already held for this caller (including one the owner approved from the queue), or for `follow_up`
        any follow-up already logged for this caller. Unknown callers are never deduplicated.
        """
        if contact_id is None:
            return None
        lo = (received_at - timedelta(hours=window_hours)).astimezone(UTC).isoformat()
        hi = received_at.astimezone(UTC).isoformat()
        win = "i.contact_id = ? AND i.intake_id != ? AND i.received_at >= ? AND i.received_at <= ?"
        args = (contact_id, intake_id, lo, hi)
        row = self.conn.execute(f"SELECT i.intake_id FROM intakes i WHERE {win} AND i.route = ? ORDER BY i.received_at LIMIT 1",
                                (*args, route)).fetchone()
        if row is None and route == "book":
            row = self.conn.execute(f"SELECT i.intake_id FROM bookings b JOIN intakes i ON i.intake_id = b.intake_id WHERE {win} "
                                    "ORDER BY i.received_at LIMIT 1", args).fetchone()
        if row is None and route == "follow_up":
            row = self.conn.execute(f"SELECT i.intake_id FROM outbox o JOIN intakes i ON i.intake_id = o.intake_id WHERE {win} "
                                    "AND o.kind = 'follow_up' AND o.status != 'suppressed_duplicate' ORDER BY i.received_at LIMIT 1",
                                    args).fetchone()
        return str(row["intake_id"]) if row else None

    def remember_intake(self, intake_id: str, contact_id: str | None, received_at: datetime, route: str, outcome: str, payload: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO intakes (intake_id, contact_id, received_at, route, outcome, payload) VALUES (?,?,?,?,?,?)",
                              (intake_id, contact_id, received_at.astimezone(UTC).isoformat(), route, outcome, payload))

    def intake_payload(self, intake_id: str) -> str:
        row = self.conn.execute("SELECT payload FROM intakes WHERE intake_id = ?", (intake_id,)).fetchone()
        if row is None:
            raise QueueError(f"no stored intake {intake_id!r}")
        return str(row["payload"])

    # -- synthetic calendar (D-21) ---------------------------------------------

    def book_first_free(self, intake_id: str, contact_id: str | None, after: datetime, tz: str, slot_times: list[str],
                        days_ahead: int) -> tuple[str, datetime]:
        zone = ZoneInfo(tz)
        local = after.astimezone(zone)
        day = local.date()
        found = 0
        while found < days_ahead:
            day = day + timedelta(days=1)
            if day.weekday() >= 5:  # Mon-Fri only
                continue
            found += 1
            for t in slot_times:
                hh, mm = (int(x) for x in t.split(":"))
                start = datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)
                taken = self.conn.execute("SELECT 1 FROM bookings WHERE slot_start = ?", (start.isoformat(),)).fetchone()
                if taken is None:
                    bid = new_id("bk")
                    with self.conn:
                        self.conn.execute("INSERT INTO bookings (booking_id, intake_id, contact_id, slot_start, calendar, created_at) VALUES (?,?,?,?,?,?)",
                                          (bid, intake_id, contact_id, start.isoformat(), "synthetic", now_iso()))
                    return bid, start
        raise LookupError(f"no free synthetic slot in the next {days_ahead} business days")

    def bookings(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM bookings ORDER BY slot_start")]

    # -- escalation queue (D-20) ------------------------------------------------

    def enqueue(self, intake_id: str, contact_id: str | None, proposed_action: str, why: str, reasons: list[str]) -> str:
        qid = new_id("q")
        with self.conn:
            self.conn.execute(
                "INSERT INTO queue (queue_id, intake_id, contact_id, proposed_action, why, reasons, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (qid, intake_id, contact_id, proposed_action, why, json.dumps(reasons), "pending", now_iso()))
        return qid

    def queue(self, status: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM queue", tuple[str, ...]()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        out = []
        for r in self.conn.execute(sql + " ORDER BY created_at, queue_id", args):
            d = dict(r)
            d["reasons"] = json.loads(d["reasons"])
            out.append(d)
        return out

    def queue_item(self, queue_id: str) -> dict[str, Any]:
        r = self.conn.execute("SELECT * FROM queue WHERE queue_id = ?", (queue_id,)).fetchone()
        if r is None:
            raise QueueError(f"no queue item {queue_id!r}")
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"])
        return d

    def decide(self, queue_id: str, status: str, action: str | None, note: str | None) -> dict[str, Any]:
        item = self.queue_item(queue_id)
        if item["status"] != "pending":
            raise QueueError(f"queue item {queue_id} is already {item['status']}")
        with self.conn:
            self.conn.execute("UPDATE queue SET status = ?, decided_action = ?, decided_note = ?, decided_at = ? WHERE queue_id = ?",
                              (status, action, note, now_iso(), queue_id))
        return self.queue_item(queue_id)
