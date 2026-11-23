"""`intake-desk` command line.

    intake-desk demo                       one-command walkthrough on a throwaway store (README "Demo")
    intake-desk eval [--threshold 0.7]     all 40 labeled intakes → docs/eval-report.md (AC5)
    intake-desk route --case i24           one fixture intake through the desk
    intake-desk queue list|approve|reject  the escalation queue of a run's desk store
    intake-desk serve                      the FastAPI webhooks on localhost (recorded router)

Every run is on the recorded router unless --live is given, which needs ANTHROPIC_API_KEY (D-6).
Nothing is ever sent: outbound goes to the desk store's outbox and out/<run>/outbox.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import anyio

from intake_desk import fixtures
from intake_desk.desk import Desk, DeskConfig
from intake_desk.layer import Layer, LayerDegraded
from intake_desk.models import REPO_DIR, Outcome
from intake_desk.report import run_eval, write
from intake_desk.router import AgentSdkRouter, LiveCallRefused, RecordedRouter, RecordingRouter, Router
from intake_desk.store import QueueError, Store

OUT = REPO_DIR / "out"
DEMO_CASES = ("i01", "i11", "i24", "i29", "i12", "i38", "i40")


def _threshold(arg: float | None) -> float | None:
    if arg is not None:
        return arg
    env = os.environ.get("G4_THRESHOLD")
    return float(env) if env else None


def _router(live: bool, record: str | None) -> Router:
    if not live:
        return RecordedRouter()
    r: Router = AgentSdkRouter()
    return RecordingRouter(r, Path(record)) if record else r


def _open(run_id: str, g0_db: str | None, fresh: bool, threshold: float | None, live: bool = False, record: str | None = None,
          out: Path = OUT) -> Desk:
    run_dir = out / run_id
    if fresh and run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    layer = Layer(db_path=g0_db or str(run_dir / "layer.sqlite"))
    layer.require_healthy()
    store = Store(run_dir / "desk.sqlite", jsonl=run_dir / "outbox.jsonl")
    return Desk(layer, store, _router(live, record), DeskConfig.load(threshold=_threshold(threshold)), run_id)


def _close(desk: Desk) -> None:
    desk.store.close()
    desk.layer.close()


def _show(o: Outcome, text: str) -> None:
    d = o.decision
    r = d.router
    print(f"\n[{o.intake_id}] {text}")
    print(f"  router: {f'{r.route} ({r.confidence:.2f})' if r else 'invalid'}  →  final: {d.route.upper()}"
          f"{'  overrides: ' + ', '.join(d.overrides) if d.overrides else ''}{'  (after hours)' if o.after_hours else ''}"
          f"{'  duplicate of ' + o.duplicate_of if o.duplicate_of else ''}")
    for reason in d.reasons:
        print(f"    - {reason}")
    for x in o.outbound:
        print(f"  outbox: {x.kind} → {x.to} [{x.status}] {x.detail}")
    if o.booking_id:
        print(f"  booking: {o.booking_id} (synthetic calendar)")
    if o.queue_id:
        print(f"  queue: {o.queue_id} pending owner approve/reject")


async def _demo(args: argparse.Namespace) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="g4-demo-"))
    desk = _open("demo", str(tmp / "layer.sqlite"), True, args.threshold, out=tmp)
    try:
        intakes, labels = fixtures.load()
        by_id = {i.id: i for i in intakes}
        print(f"G4·C intake desk demo — recorded router (no model call, $0), threshold {desk.config.threshold:.2f}. Nothing is sent.")
        print("G0 health:", desk.layer.health().status)
        outcomes = {}
        for cid in sorted(DEMO_CASES, key=lambda c: by_id[c].received_at):
            outcomes[cid] = await desk.process(by_id[cid])
            _show(outcomes[cid], by_id[cid].text)
        print("\nOwner decisions:")
        low = outcomes["i12"].queue_id
        emer = outcomes["i24"].queue_id
        if low:
            desk.reject(low, "unknown number, no request stated; nothing to act on")
            print(f"  reject  {low} (i12, low confidence, unknown caller) → closed, nothing sent")
        if emer:
            desk.approve(emer, None, "on-call tech dispatched by phone")
            print(f"  approve {emer} (i24, emergency) as owner_handled → nothing sent to the customer")
        print("\nOutbox (every row logged, none sent):")
        for x in desk.store.outbox():
            print(f"  {x.intake_id:4} {x.kind:21} {x.channel:8} {x.status}")
        print("\nFull labeled set:")
        full = _open("demo-eval", str(tmp / "layer-eval.sqlite"), True, args.threshold, out=tmp)
        try:
            ev = await run_eval(full, intakes, labels)
            m = ev.current
            print(f"  accuracy {ev.g0_correct}/{m.n} · escalation rate {m.escalated}/{m.n} · missed emergencies {len(m.missed_emergencies)} "
                  f"(router alone missed {len(m.missed_router_only)}) — on hand-written recorded responses, not a model")
        finally:
            _close(full)
        return 0
    finally:
        _close(desk)
        shutil.rmtree(tmp, ignore_errors=True)


async def _eval(args: argparse.Namespace) -> int:
    desk = _open(args.run_id, args.g0_db, True, args.threshold, args.live, args.record, out=Path(args.out))
    try:
        intakes, labels = fixtures.load()
        ev = await run_eval(desk, intakes, labels)
        path = write(ev, args.run_id, Path(args.report))
        m = ev.current
        print(json.dumps({
            "run_id": args.run_id, "router": ev.router_name, "threshold": m.threshold, "intakes": m.n,
            "accuracy": round(ev.g0_correct / m.n, 4), "router_accuracy": round(m.router_accuracy, 4),
            "escalation_rate": round(m.escalation_rate, 4), "missed_emergencies": len(m.missed_emergencies),
            "router_only_missed_emergencies": len(m.missed_router_only), "booked_below_threshold": len(m.auto_booked_below_threshold),
            "sweep": [{"threshold": s.threshold, "accuracy": round(s.accuracy, 4), "escalation_rate": round(s.escalation_rate, 4),
                       "missed_emergencies": len(s.missed_emergencies)} for s in ev.sweep],
            "cost_usd": ev.run_total["cost_usd"], "report": str(path)}, indent=2))
        return 3 if m.missed_emergencies else 0
    finally:
        _close(desk)


async def _route(args: argparse.Namespace) -> int:
    desk = _open(args.run_id, args.g0_db, False, args.threshold, args.live, out=Path(args.out))
    try:
        intakes, _ = fixtures.load()
        match = [i for i in intakes if i.id == args.case]
        if not match:
            print(f"no fixture intake {args.case!r}", file=sys.stderr)
            return 2
        o = await desk.process(match[0])
        _show(o, match[0].text)
        return 0
    finally:
        _close(desk)


def _queue(args: argparse.Namespace) -> int:
    desk = _open(args.run_id, args.g0_db, False, None, out=Path(args.out))
    try:
        res: Any
        if args.action == "list":
            res = desk.store.queue(args.status)
        elif args.action == "approve":
            res = desk.approve(args.queue_id, args.as_action, args.note)
        else:
            res = desk.reject(args.queue_id, args.note)
        print(json.dumps(res, indent=2, default=str))
        return 0
    except QueueError as e:
        print(str(e), file=sys.stderr)
        return 2
    finally:
        _close(desk)


def _serve(args: argparse.Namespace) -> int:  # pragma: no cover - manual use
    import uvicorn

    from intake_desk.app import create_app

    run_dir = Path(args.out) / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(g0_db=args.g0_db or str(run_dir / "layer.sqlite"), desk_db=run_dir / "desk.sqlite",
                     threshold=_threshold(args.threshold), live=args.live, run_id=args.run_id)
    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="intake-desk", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser, run_id: str) -> None:
        sp.add_argument("--run-id", default=run_id)
        sp.add_argument("--out", default=str(OUT), help="run directory root (default out/)")
        sp.add_argument("--g0-db", default=None, help="G0 SQLite file (default out/<run>/layer.sqlite)")

    d = sub.add_parser("demo", help="one-command walkthrough")
    d.add_argument("--threshold", type=float, default=None)

    e = sub.add_parser("eval", help="all labeled intakes → report")
    common(e, "eval")
    e.add_argument("--threshold", type=float, default=None)
    e.add_argument("--report", default=str(REPO_DIR / "docs" / "eval-report.md"))
    e.add_argument("--live", action="store_true", help="Claude Agent SDK router; needs ANTHROPIC_API_KEY (not used in this build)")
    e.add_argument("--record", default=None, help="with --live: save responses in the recorded file's shape")

    r = sub.add_parser("route", help="one fixture intake")
    common(r, "manual")
    r.add_argument("--case", required=True)
    r.add_argument("--threshold", type=float, default=None)
    r.add_argument("--live", action="store_true")

    q = sub.add_parser("queue", help="escalation queue of a run")
    common(q, "manual")
    q.add_argument("action", choices=["list", "approve", "reject"])
    q.add_argument("queue_id", nargs="?")
    q.add_argument("--status", choices=["pending", "approved", "rejected"], default=None)
    q.add_argument("--as", dest="as_action", choices=["book", "follow_up", "owner_handled"], default=None)
    q.add_argument("--note", default=None)

    s = sub.add_parser("serve", help="FastAPI webhooks on 127.0.0.1")
    common(s, "api")
    s.add_argument("--port", type=int, default=8040)
    s.add_argument("--threshold", type=float, default=None)
    s.add_argument("--live", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "threshold", None) is not None and not 0.0 <= args.threshold <= 1.0:
        print("--threshold must be within 0..1", file=sys.stderr)
        return 2
    if args.cmd == "queue" and args.action in ("approve", "reject") and not args.queue_id:
        print("queue approve/reject needs a queue id", file=sys.stderr)
        return 2
    try:
        if args.cmd == "demo":
            return int(anyio.run(_demo, args))
        if args.cmd == "eval":
            return int(anyio.run(_eval, args))
        if args.cmd == "route":
            return int(anyio.run(_route, args))
        if args.cmd == "queue":
            return _queue(args)
        return _serve(args)
    except LiveCallRefused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except LayerDegraded as e:
        print(f"shared layer not ready: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
