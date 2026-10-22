"""``runeforge`` command line."""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.table import Table

from runeforge import canon
from runeforge.ledger import LedgerUnreadable
from runeforge.paths import LEDGER_PATH, REPO_ROOT

console = Console(soft_wrap=True)


def cmd_canon(args: argparse.Namespace) -> int:
    try:
        lp2 = canon.load_lp2()
        lp1 = canon.load_lp1()
        solved = canon.load_solved_sections()
    except canon.CanonIntegrityError as exc:
        console.print(f"[red]CANON INTEGRITY FAILURE[/red]: {exc}")
        return 2
    pins = canon.read_pins()
    console.print(f"numbering      : {lp2.numbering} (book page = LP2 page + 17); {lp1.numbering}")
    console.print(f"LP2 runes      : {lp2.stream().size:,} on {len(lp2.pages)} pages")
    console.print(
        f"unsolved runes : {canon.unsolved_stream().size:,} (pages 0-55; page 50 runeless)"
    )
    console.print(f"LP1 runes      : {lp1.stream().size:,}; solved sections: {len(solved)}")
    for p in pins.values():
        console.print(f"  {p.sha256}  {p.name} {p.note}")
    console.print("[green]pins verified[/green]")
    if args.rebuild:
        r = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "build_canon.py"), "--check"]
        )
        return r.returncode
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from runeforge import stats

    secs = canon.unsolved_sections()
    rows = {"ALL (pages 0-55)": canon.unsolved_stream(), **secs}
    out = {}
    t = Table(title="LP2 unsolved fingerprint")
    for col in (
        "stream",
        "n",
        "IoC·29",
        "entropy",
        "χ² (df 28)",
        "doublets",
        "dbl z",
        "per. max z",
        "κ max z",
    ):
        t.add_column(col, justify="right")
    for name, x in rows.items():
        s = stats.summary(x)
        max_p = 600 if name.startswith("ALL") else 400
        per = stats.scan(x, max_p, "periodic")
        kap = stats.scan(x, max_p, "kappa")
        out[name] = {
            **s,
            "periodic": {k: per[k] for k in ("max_z", "argmax", "familywise_bar", "peak")},
            "kappa": {k: kap[k] for k in ("max_z", "argmax", "familywise_bar", "peak")},
        }
        t.add_row(
            name,
            f"{s['n']:,}",
            f"{s['ioc_norm']:.3f}",
            f"{s['entropy_bits']:.3f}",
            f"{s['chi2_uniform']:.1f}",
            f"{s['doublets']}",
            f"{s['doublet_z']:.1f}",
            f"{per['max_z']:.2f}{' !' if per['peak'] else ''}",
            f"{kap['max_z']:.2f}{' !' if kap['peak'] else ''}",
        )
    scan = stats.shared_key_scan(secs)
    cross = stats.familywise([r for r in scan if r["a"] != r["b"]])
    within = stats.familywise([r for r in scan if r["a"] == r["b"]])
    out["shared_keystream"] = {
        "cross": {k: v for k, v in cross.items() if k != "best"},
        "within": {k: v for k, v in within.items() if k != "best"},
    }
    if args.json:
        print(json.dumps(out, indent=1, default=float))
        return 0
    console.print(t)
    console.print(
        f"shared-keystream scan: cross-section max z {cross['max_z']:.2f} over "
        f"{cross['n_tests']:,} shifts -> family-wise p {cross['p_familywise']:.2f}; "
        f"within-section (|shift|>=2) max z "
        f"{within['max_z']:.2f} -> p {within['p_familywise']:.2f}"
    )
    console.print("'!' marks a peak above the family-wise (Bonferroni, alpha 1e-3) bar.")
    return 0


def cmd_solved(_: argparse.Namespace) -> int:
    from runeforge.interrupts import decode_rigid, decode_skip_known
    from runeforge.transforms import from_method

    t = Table(title="Solved sections (Rule 1)")
    for col in ("section", "pages", "method", "runes", "interrupts", "reproduces", "rigid"):
        t.add_column(col)
    ok_all = True
    for s in canon.load_solved_sections():
        tr = from_method(s.method)
        ok = np.array_equal(decode_skip_known(s.cipher, tr, s.interrupts), s.plain)
        rigid = np.array_equal(decode_rigid(s.cipher, tr), s.plain)
        ok_all &= ok
        t.add_row(
            s.id,
            f"{s.numbering.split('-')[0]} {','.join(map(str, s.pages))}",
            s.method["label"][:40],
            str(s.cipher.size),
            str(len(s.interrupts)),
            "[green]yes[/green]" if ok else "[red]NO[/red]",
            "yes" if rigid else "no",
        )
    console.print(t)
    return 0 if ok_all else 1


def _ledger(args):
    from runeforge.ledger import Ledger

    return Ledger(getattr(args, "ledger", None) or LEDGER_PATH)


OPEN = ("never-run", "running", "parked", "hit-unverified")
TARGET_SPLIT = {"instrument": 30, "bounded": 40, "redteam": 20, "closeout": 10}


def cmd_status(args: argparse.Namespace) -> int:
    from runeforge.runner.jobs import RUNS_DIR, pid_alive_runeforge

    ledger = _ledger(args)
    rows = ledger.rows()
    latest = ledger.latest()
    if args.grep:
        needle = args.grep.lower()
        hits = [r for r in rows if needle in _values_text(r)]
        for r in hits:
            console.print(
                f"{r.recorded}  {r.lane_id:28s} {r.status:15s} {r.verdict or '':22s} "
                f"{(r.hypothesis or '')[:70]}"
            )
        console.print(f"{len(hits)} row(s) match {args.grep!r} (values only); numbering LP2-0-57")
        return 0
    if args.round:
        rounds = sorted({r.round for r in rows if r.round}, key=_natural)
        rnd = args.round if args.round != "latest" else (rounds[-1] if rounds else None)
        lanes = [r for r in latest.values() if rnd is None or r.round == rnd]
        counts = {c: 0 for c in TARGET_SPLIT}
        hours = {c: 0.0 for c in TARGET_SPLIT}
        for r in lanes:
            if r.category:
                counts[r.category] += 1
                hours[r.category] += _lane_hours([x for x in rows if x.lane_id == r.lane_id])
        total_h = sum(hours.values())
        total_n = sum(counts.values())
        console.print(
            f"round {rnd or '(all)'}: {total_n} lane(s), {total_h:.1f} h recorded; "
            "numbering LP2-0-57"
        )
        for c, target in TARGET_SPLIT.items():
            share = 100 * (
                hours[c] / total_h if total_h else (counts[c] / total_n if total_n else 0)
            )
            console.print(
                f"  {c:10s} {counts[c]:3d} lane(s) {hours[c]:7.1f} h  {share:5.1f} % "
                f"(target {target} %, {share - target:+.1f})"
            )
        if total_n:
            gaps = {
                c: TARGET_SPLIT[c] - 100 * (hours[c] / total_h if total_h else counts[c] / total_n)
                for c in TARGET_SPLIT
            }
            console.print(f"furthest below its share: {max(gaps, key=gaps.get)}")
        else:
            console.print("no categorised lanes yet: every category is below its share")
        return 0
    # default / --short
    open_rows = [r for r in latest.values() if r.status in OPEN]
    console.print(
        f"ledger {ledger.path}: {len(rows)} row(s), {len(latest)} lane(s); numbering LP2-0-57"
    )
    console.print(f"open lanes: {len(open_rows)}")
    for r in open_rows:
        cursor = ""
        if isinstance(r.parked_state, dict) and "cursor" in r.parked_state:
            cursor = f" cursor {r.parked_state['cursor']}"
        console.print(f"  {r.lane_id:28s} {r.status:14s} control={r.positive_control}{cursor}")
    jobs = []  # every run with a status.json; the runner removes sweep.pid when it exits
    for st in sorted(RUNS_DIR.glob("*/status.json")):
        try:
            info = json.loads(st.read_text())
        except (OSError, ValueError):
            continue
        pidfile = st.parent / "sweep.pid"
        try:
            pid = int(pidfile.read_text().strip()) if pidfile.exists() else int(info.get("pid", 0))
        except (OSError, ValueError):
            pid = 0
        alive = bool(pid) and pid_alive_runeforge(pid, info)
        jobs.append((st.parent.name, pid, alive, info))
    console.print(f"jobs: {sum(1 for j in jobs if j[2])} alive, {len(jobs)} with a status.json")
    for name, pid, alive, info in jobs:
        rate = info.get("seeds_per_s")
        frac = info.get("fraction")
        best = info.get("best_score")
        console.print(
            f"  {name:28s} pid {pid:<8d} {'ALIVE' if alive else 'dead '} "
            f"cursor {info.get('cursor')} ({'?' if frac is None else f'{100 * frac:.2f} %'}) "
            f"{'?' if rate is None else f'{rate:,.0f}'} seeds/s crossers {info.get('crossers')} "
            f"best {'?' if best is None else f'{best:.4f}'} done {info.get('done')} "
            f"kill {info.get('kill_condition')}"
        )
        if (
            not alive
            and not info.get("done")
            and latest.get(name)
            and latest[name].status == "running"
        ):
            console.print(
                "    [yellow]dead PID with a running row: park it with its cursor[/yellow]"
            )
    if not args.short:
        t = Table(title="last rows")
        for col in ("recorded", "lane", "status", "verdict", "control", "threshold"):
            t.add_column(col)
        for r in rows[-5:]:
            t.add_row(
                r.recorded,
                r.lane_id,
                r.status,
                r.verdict or "",
                r.positive_control,
                "" if r.threshold is None else str(r.threshold),
            )
        console.print(t)
    else:
        for r in rows[-5:]:
            console.print(f"  {r.recorded} {r.lane_id} -> {r.status} {r.verdict or ''}")
    return 0


def _values_text(row) -> str:
    """A row's values (not its field names) as lowercase text, for --grep."""

    def flat(v):
        if isinstance(v, dict):
            return " ".join(flat(x) for x in v.values())
        if isinstance(v, list):
            return " ".join(flat(x) for x in v)
        return "" if v is None else str(v)

    return flat(row.model_dump()).lower()


def _natural(s: str):
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def _lane_hours(lane_rows) -> float:
    """Hours of compute: each running row's start to the next final row's finish."""
    from datetime import datetime

    total, start = 0.0, None
    for r in lane_rows:
        if r.status == "running" and r.started:
            start = r.started
        elif start and r.finished and r.status != "running":
            with contextlib.suppress(ValueError):
                total += (
                    datetime.fromisoformat(r.finished) - datetime.fromisoformat(start)
                ).total_seconds() / 3600
            start = None
    return total


def _parse_sets(pairs: list[str]) -> dict:
    out = {}
    for item in pairs or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"--set expects key=value, got {item!r}")
        try:
            out[key] = json.loads(value)
        except json.JSONDecodeError:
            out[key] = value
    return out


def _prereg_fields(lane_path: str) -> dict:
    """The pre-registration row a lane YAML implies: the bar it froze, its N, category and
    control spec, so the row and the YAML cannot drift apart."""
    from runeforge.lanes import load_lane

    lane = load_lane(lane_path)
    out = {
        "lane_id": lane.lane_id,
        "hypothesis": lane.hypothesis,
        "family": lane.family,
        "category": lane.category,
        "prereg": lane.prereg,
        "n_trials": lane.n_trials,
        "claim_bar": lane.claim_bar,
        "family_wise_bar": lane.family_wise_bar,
        "control_spec": lane.control.model_dump(),
        "params": {
            "lane_yaml": str(lane_path),
            "generator": lane.generator,
            "generator_params": lane.generator_params,
            "seed_range": list(lane.seed_range),
            "ciphertext_view": lane.ciphertext_view,
            "combine": lane.combine,
            "filter_model": lane.filter_model,
            "preset": lane.preset,
            "window": lane.window,
            "pages": lane.pages,
        },
    }
    if lane.family_wise_bar is not None:
        out["threshold"] = lane.family_wise_bar
        out["threshold_fixed_in_advance"] = True
    return out


def cmd_ledger(args: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from runeforge.ledger import to_upstream

    ledger = _ledger(args)
    fields = {}
    if getattr(args, "json", None):
        if args.json == "-":
            src = sys.stdin.read()
        else:
            with open(args.json, encoding="utf-8") as fh:
                src = fh.read()
        fields.update(json.loads(src))
    if getattr(args, "lane", None):
        fields = {**_prereg_fields(args.lane), **fields}
    fields.update(_parse_sets(getattr(args, "set", None)))
    try:
        if args.action == "append":
            lane_id = args.lane_id or fields.pop("lane_id", None)
            if not lane_id:
                raise SystemExit("append needs a lane id")
            fields.pop("lane_id", None)
            hyp, fam = fields.pop("hypothesis", None), fields.pop("family", None)
            if not hyp or not fam:
                raise SystemExit("append needs hypothesis and family (--set or --json)")
            row = ledger.new(lane_id, hyp, fam, **fields)
        elif args.action == "update":
            fields.pop("lane_id", None)
            row = ledger.update(args.lane_id, **fields)
        else:  # show
            row = ledger.get(args.lane_id)
            if row is None:
                console.print(f"no lane {args.lane_id}")
                return 1
            data = to_upstream(row) if args.upstream else row.model_dump()
            print(json.dumps(data, indent=1, default=str))
            return 0
    except (ValidationError, ValueError) as exc:
        console.print(f"[red]refused[/red]: {exc}")
        return 2
    console.print(f"appended {row.lane_id} -> {row.status} ({ledger.path})")
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    from runeforge.queue import load_queue

    try:
        entries = load_queue()
    except ValueError as exc:
        console.print(f"[red]queue.json invalid[/red]: {exc}")
        return 2
    latest = _ledger(args).latest()
    console.print(
        f"queue.json: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}; "
        "numbering LP2-0-57"
    )
    if not entries:
        console.print("  none (Hunter approves lanes here; the loop never invents one)")
        return 0
    for e in entries:
        st = latest[e.id].status if e.id in latest else "no row"
        console.print(
            f"  {e.id:28s} {e.category:10s} approved={e.approved!s:5s} "
            f"gpu_hours_cap={e.gpu_hours_cap} prereg_ready={e.prereg_ready} ledger={st}"
        )
    nxt = [
        e
        for e in entries
        if e.approved
        and (latest.get(e.id) is None or latest[e.id].status in ("never-run", "parked"))
    ]
    console.print(f"next runnable: {nxt[0].id if nxt else 'none'}")
    return 0


def cmd_oracle(args: argparse.Namespace) -> int:
    from runeforge import oracle

    argv = ["--selftest"] if args.selftest else ["--regression"]
    return oracle.main(argv)


def cmd_lane(args: argparse.Namespace) -> int:
    from runeforge.lanes import load_lane

    try:
        lane = load_lane(args.path)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]invalid lane spec[/red] {args.path}: {exc}")
        return 2
    console.print(f"{lane.lane_id}: valid lane spec, {lane.n_trials:,} trials")
    problems = lane.runnable_problems()
    for p in problems:
        console.print(f"  [yellow]not runnable[/yellow]: {p}")
    return 1 if problems else 0


def cmd_gate(args: argparse.Namespace) -> int:
    from runeforge.lanes import load_lane
    from runeforge.runner import gate
    from runeforge.runner.sweep import run_dir

    try:
        lane = load_lane(args.lane)
        res = gate.run_gate(lane, seeds=args.seeds, corpus=args.corpus)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]REFUSED:[/red] {exc}")
        return 2
    mark = {"PASS": ".", "FAIL": "F", "FAIL(soft)": "f", "INFO": "i"}
    first = res.per_seed_rows[0] if res.per_seed_rows else []
    console.print(
        f"{lane.lane_id}: fingerprint gate over {len(res.per_seed_rows)} keys (numbering: LP2-0-57)"
    )
    console.print("  per key: . pass  F fail  f soft fail  i info")
    for j, r0 in enumerate(first):
        marks = "".join(mark.get(rows[j].verdict, "?") for rows in res.per_seed_rows)
        console.print(f"  {r0.id:36s} LP2 {r0.lp2!s:>8}  band {r0.band:38s} {marks}")
    out = gate.write_report(lane, res, run_dir(lane))
    console.print(
        f"fails per constraint over {args.seeds} keys: {res.fails_per_constraint or 'none'}"
    )
    console.print(res.verdict_line)
    if res.verdict_line.startswith("GATE FAIL"):
        console.print("verdict: EXCLUDED (gate) -- excludes the typical key, not the family")
    console.print(f"wrote {out}")
    return 1 if res.verdict_line.startswith("GATE FAIL") else 0


def cmd_control(args: argparse.Namespace) -> int:
    from runeforge.lanes import load_lane
    from runeforge.runner import control
    from runeforge.runner.sweep import run_dir

    try:
        lane = load_lane(args.lane)
        rep = control.run_control(lane, seed=args.seed)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]REFUSED:[/red] {exc}")
        return 2
    for p in rep.plants:
        console.print(
            f"  seed {p.seed:>12d} offset {p.offset:5d} rank {p.rank:4d} recovery {p.recovery:.3f} "
            f"planted {p.planted_score:.4f} best decoy {p.best_decoy:.4f} ceiling {p.ceiling:.4f}"
        )
    console.print(rep.summary())
    for reason in rep.reasons:
        console.print(f"  [yellow]{reason}[/yellow]")
    if rep.status != "passed":
        console.print(
            f"lane verdict if it stops here: {rep.verdict_if_failed} (do not lower the bar)"
        )
    if args.out:  # a replay (verify-lane): never touches the lane's evidence or the ledger
        out = Path(args.out)
        detail = control.write_report(rep, lane, out, lanes_dir=out / "lanes")
        console.print(f"replay written under {out} (lane evidence and ledger untouched)")
        return 0 if rep.status == "passed" else 1
    detail = control.write_report(rep, lane, run_dir(lane))
    console.print(f"wrote {detail['path']} (sha256 {detail['sha256'][:12]}); commit it")
    ledger = _ledger(args)
    if ledger.get(lane.lane_id, strict=False) is None:
        console.print(
            f"[yellow]not recorded: no ledger row for {lane.lane_id}; append one "
            "(`runeforge ledger append`) and re-run the control[/yellow]"
        )
    else:
        ledger.update(
            lane.lane_id,
            positive_control=rep.status,
            control_detail=detail,
            control_spec=lane.control.model_dump(),
        )
        console.print(f"ledger: {lane.lane_id} positive_control={rep.status}")
    return 0 if rep.status == "passed" else 1


def cmd_null(args: argparse.Namespace) -> int:
    from runeforge.lanes import load_lane
    from runeforge.runner import null
    from runeforge.runner.sweep import run_dir

    try:
        lane = load_lane(args.lane)
        rep = null.run_null(lane, n=args.n, seed=args.seed, trials=args.trials)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]REFUSED:[/red] {exc}")
        return 2
    out = null.write_report(lane, rep, run_dir(lane))
    n1, n2 = rep["null1_shuffle"], rep["null2_sha256"]
    console.print(
        f"{lane.lane_id}: nulls at window {lane.window}, preset {lane.preset}, "
        f"{rep['trials_per_replicate']:,} trials per replicate "
        f"(lane N {lane.n_trials:,}); numbering LP2-0-57"
    )
    for label, x in (
        ("Null 1, size-matched shuffle of the real runes", n1),
        ("Null 2, domain-separated SHA-256 stream", n2),
    ):
        console.print(
            f"- {label}: n = {x['n']}, mean {x['mean']:.4f}, sd {x['sd']:.4f}, max {x['max']:.4f}"
        )
    if rep["same_trial_count"] and lane.n_trials < 1000:
        console.print(
            f"small N: python scripts/threshold_for.py --n {lane.n_trials} --preset {lane.preset} "
            f"--L {lane.window} --null-max {n1['max']:.4f} --null2-max {n2['max']:.4f}"
        )
    console.print(f"wrote {out}; commit it")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    from runeforge.lanes import load_lane
    from runeforge.runner import rescore

    lane = load_lane(args.lane)
    lo, hi = rescore.parse_seeds(args.seeds)
    out = rescore.score_range(lane, lo, hi, top=args.top)
    if args.json:
        console.print(json.dumps(out, indent=1))
        return 0
    console.print(
        f"{lane.lane_id} seeds {lo}:{hi} ({hi - lo:,}) window {lane.window} preset {lane.preset}; "
        "numbering LP2-0-57"
    )
    for t in out["top"]:
        console.print(f"  seed {t['seed']:>12d}  score {t['score']:.10f}")
    console.print(
        f"above claim bar {lane.claim_bar}: {out['above_claim_bar']}; "
        f"above family-wise bar {lane.family_wise_bar}: {out['above_family_wise_bar']}"
    )
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    from runeforge.runner import sweep

    if args.backend == "gpu":
        console.print("[red]the GPU backend is Phase 3 (runeforge/gpu); use --backend cpu[/red]")
        return 2
    ledger = Path(args.ledger) if args.ledger else None
    kw = {"max_seeds": args.max_seeds, "override_q5": args.override_q5}
    if args.detach:
        return sweep.launch_detached(Path(args.lane), not args.no_resume, False, ledger, **kw)
    return sweep.run(Path(args.lane), not args.no_resume, False, ledger, **kw)


def cmd_crosser(args: argparse.Namespace) -> int:
    from runeforge.runner import crosser

    if args.action == "list":
        pending, resolved = crosser.pending_list(), crosser.resolved_list()
        console.print(f"open (FLAGGED-FOR-ORACLE): {len(pending)}; numbering LP2-0-57")
        for p in pending:
            console.print(f"  {p}")
        if args.all:
            console.print(f"resolved (NOISE-CROSSER / PARITY-FAIL): {len(resolved)}")
            for p in resolved:
                console.print(f"  {p}")
        return 0
    if not args.kid:
        console.print(
            f"[red]crosser {args.action} needs a crosser id (runeforge crosser list)[/red]"
        )
        return 2
    fn = {"replay": crosser.replay, "escalate": crosser.escalate, "reencipher": crosser.reencipher}
    try:
        out = fn[args.action](args.kid)
    except FileNotFoundError as exc:
        console.print(f"[red]REFUSED:[/red] {exc}")
        return 2
    console.print(json.dumps(out, indent=1, default=float))
    return crosser.exit_code(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="runeforge", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("canon", help="verify the pinned canon and print its SHA-256s")
    p.add_argument("--verify", action="store_true", help="(default) assert the pins")
    p.add_argument("--rebuild", action="store_true", help="also rebuild from data/raw and compare")
    p.set_defaults(fn=cmd_canon)
    p = sub.add_parser("stats", help="statistical fingerprint of the unsolved pages")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("solved", help="reproduce the nine solved sections")
    p.set_defaults(fn=cmd_solved)
    p = sub.add_parser("status", help="the ledger: open lanes, jobs, last rows")
    p.add_argument("--short", action="store_true")
    p.add_argument("--round", nargs="?", const="latest", help="budget split for a round")
    p.add_argument("--grep", help="rows mentioning this text")
    p.add_argument("--ledger", default=str(LEDGER_PATH))
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("ledger", help="append or update ledger rows (append-only)")
    p.add_argument("action", choices=("append", "update", "show"))
    p.add_argument("lane_id", nargs="?")
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="JSON values allowed")
    p.add_argument("--json", help="a JSON object of fields (file or - for stdin)")
    p.add_argument("--upstream", action="store_true", help="show: Dukotah LEDGER.json shape")
    p.add_argument(
        "--lane", help="append: pre-register from this lane YAML (bar, N, category, control)"
    )
    p.add_argument("--ledger", default=str(LEDGER_PATH))
    p.set_defaults(fn=cmd_ledger)
    p = sub.add_parser("queue", help="queue.json joined with ledger status")
    p.add_argument("--ledger", default=str(LEDGER_PATH))
    p.set_defaults(fn=cmd_queue)
    p = sub.add_parser("oracle", help="oracle regression check / self-test")
    p.add_argument("--selftest", action="store_true")
    p.set_defaults(fn=cmd_oracle)
    p = sub.add_parser("lane", help="validate a lane YAML")
    p.add_argument("path")
    p.set_defaults(fn=cmd_lane)
    p = sub.add_parser("gate", help="fingerprint pre-filter: simulate the family on English")
    p.add_argument("lane")
    p.add_argument("--seeds", type=int, default=12)
    p.add_argument("--corpus", default="cicada-english")
    p.set_defaults(fn=cmd_gate)
    p = sub.add_parser("control", help="planted positive through the lane's exact pipeline")
    p.add_argument("lane")
    p.add_argument("--seed", type=int, default=3301, help="rng seed of plants and decoys")
    p.add_argument("--ledger", help="record the result in this ledger (default ledger/)")
    p.add_argument(
        "--out", help="replay: write the report under this directory only (no ledger, no lanes/)"
    )
    p.set_defaults(fn=cmd_control)
    p = sub.add_parser("null", help="the lane's two nulls (shuffle, SHA-256) for PREREG/RESULTS")
    p.add_argument("lane")
    p.add_argument("--n", type=int, default=200, help="replicates (>= 200)")
    p.add_argument("--trials", type=int, help="keys per replicate (default min(N, 1000))")
    p.add_argument("--seed", type=int, default=3301)
    p.set_defaults(fn=cmd_null)

    p = sub.add_parser("score", help="re-score seeds with the lane's sweep pipeline")
    p.add_argument("lane")
    p.add_argument("seeds", help="a seed, or lo:hi")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("sweep", help="run a lane (checkpoint/resume; --detach for long runs)")
    p.add_argument("lane")
    p.add_argument("--detach", action="store_true")
    p.add_argument("--resume", action="store_true", help="(default)")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--backend", choices=("cpu", "gpu"), default="cpu")
    p.add_argument("--max-seeds", type=int)
    p.add_argument("--ledger")
    p.add_argument(
        "--override-q5", metavar="REASON", help="resume a Q5-killed lane; the reason is recorded"
    )
    p.set_defaults(fn=cmd_sweep)
    p = sub.add_parser("crosser", help="HIT_PROTOCOL steps: replay, escalate, reencipher")
    p.add_argument("action", choices=("list", "replay", "escalate", "reencipher"))
    p.add_argument("kid", nargs="?")
    p.add_argument("--cpu", action="store_true", help="(replay always uses the CPU reference)")
    p.add_argument("--all", action="store_true", help="list: also the resolved crossers")
    p.set_defaults(fn=cmd_crosser)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except LedgerUnreadable as exc:
        print(f"ledger unreadable: {exc}", file=sys.stderr)
        print("run: python scripts/validate_ledger.py", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
