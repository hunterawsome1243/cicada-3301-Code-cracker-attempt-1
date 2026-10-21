"""``runeforge`` command line."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import numpy as np
from rich.console import Console
from rich.table import Table

from runeforge import canon
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


def cmd_status(args: argparse.Namespace) -> int:
    from runeforge.ledger import Ledger

    ledger = Ledger(args.ledger)
    rows = ledger.latest()
    if not rows:
        console.print(f"ledger {ledger.path} is empty -- no lane has been pre-registered yet")
        return 0
    t = Table(title=f"Ledger ({ledger.path})")
    for col in ("lane", "family", "status", "control", "trials", "best", "bar", "finished"):
        t.add_column(col)
    for r in rows.values():
        t.add_row(
            r.lane_id,
            r.family,
            r.status,
            r.control_result,
            f"{r.n_trials:,}",
            "" if r.best_score is None else f"{r.best_score:.3f}",
            "" if r.family_wise_bar is None else f"{r.family_wise_bar:.3f}",
            r.finished or "",
        )
    console.print(t)
    return 0


def cmd_oracle(args: argparse.Namespace) -> int:
    from runeforge import oracle

    if args.selftest:
        r = oracle.selftest()
        for name in ("correct", "wrong"):
            v = r[name]
            console.print(f"{name:7s} key -> {v.status:12s} {v.criteria}")
        console.print(
            f"ORACLE SELF-TEST: {'[green]PASS[/green]' if r['passed'] else '[red]FAIL[/red]'}"
        )
        return 0 if r["passed"] else 2
    failures = oracle.regression_failures()
    console.print(
        "regression: "
        + (
            "[green]all solved sections reproduce[/green]"
            if not failures
            else f"[red]{failures}[/red]"
        )
    )
    return 1 if failures else 0


def cmd_lane(args: argparse.Namespace) -> int:
    from runeforge.lanes import load_lane

    lane = load_lane(args.path)
    console.print(f"{lane.lane_id}: valid lane spec, {lane.n_trials:,} trials")
    for p in lane.runnable_problems():
        console.print(f"  [yellow]not runnable[/yellow]: {p}")
    return 0


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
    p = sub.add_parser("status", help="print the ledger")
    p.add_argument("--ledger", default=str(LEDGER_PATH))
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("oracle", help="oracle regression check / self-test")
    p.add_argument("--selftest", action="store_true")
    p.set_defaults(fn=cmd_oracle)
    p = sub.add_parser("lane", help="validate a lane YAML")
    p.add_argument("path")
    p.set_defaults(fn=cmd_lane)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
