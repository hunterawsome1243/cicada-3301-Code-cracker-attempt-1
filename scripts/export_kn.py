#!/usr/bin/env python3
"""Export a Kneser-Ney preset as a ``knx-1`` table and prove the file against the scorer.

    python scripts/export_kn.py --preset kn8-cicada [--out reports/kn-export/] [--L 240]

Writes ``<out>/<preset>.npz`` (the arrays; gitignored, regenerated on demand) and
``<out>/<preset>.json`` (the manifest; committed), reloads the file with
``KNScorer.load_export`` and asserts, per position and bit for bit, that the reloaded
scorer's vectorised ``logprobs`` and the scalar ``reference_logprobs`` (the lookup a CUDA
kernel implements, probing the exported open-addressing hash) equal the fitted scorer's on
1,000 random windows, 100 held-out windows (the preset's own held-out text), the all-F window,
the max-key window and one window per sparse level holding the key whose probe is the
longest. The layout invariants of docs/kn-scorer-design.md section 4 (slot count, no duplicate
key, every key within ``max_probe``) are checked on the arrays as well. Prints the file sizes,
the fingerprint and the manifest. Any mismatch exits non-zero; nothing else is written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runeforge.scoring import boundaries, kn_fit, presets  # noqa: E402
from runeforge.scoring.kn import KNScorer  # noqa: E402

EMPTY = np.uint64(kn_fit.EMPTY_KEY)


def check(cond: bool, what: str) -> None:
    if not cond:
        raise SystemExit(f"export_kn: FAIL: {what}")


def _unpack(key: int, base: int, k: int) -> list[int]:
    """The k symbols of a packed key, oldest first (section 2.1)."""
    out = []
    for _ in range(k):
        out.append(key % base)
        key //= base
    return out[::-1]


def _unextend(ext, boundary: int) -> tuple[np.ndarray, np.ndarray, bool]:
    """(runes, starts, end_boundary) whose boundary extension is ``ext`` (section 2.5)."""
    runes, starts, pending = [], [], False
    for s in ext:
        if s == boundary:
            check(not pending, "two boundary symbols in a row cannot come from a starts mask")
            pending = True
        else:
            runes.append(int(s))
            starts.append(pending)
            pending = False
    return np.array(runes, dtype=np.int64), np.array(starts, dtype=bool), pending


def heldout_source(name: str) -> list[tuple[np.ndarray, np.ndarray | None]]:
    """(runes, word_ids or None) sequences the preset never trained on: the 90/10 tail of a
    corpus preset, the excluded solved sections of an lp-solved preset."""
    spec = presets.PRESETS[name]
    out = []
    for src in spec["train"]:
        if src == "lp-solved":
            from runeforge import canon

            for sid in spec.get("exclude", []):
                out.append((canon.solved_section(sid).plain.astype(np.int64), None))
        else:
            runes, ids = presets.heldout_stream(src)
            out.append((runes.astype(np.int64), ids))
    check(bool(out), f"{name!r} has no held-out text to draw windows from")
    return out


def windows_for(scorer: KNScorer, name: str, length: int, n_random: int, n_heldout: int, seed):
    """The parity windows: ``(label, runes, kwargs)`` with ``starts`` for a wb model."""
    rng = np.random.default_rng(seed)
    wb = scorer.boundary is not None
    lengths = boundaries.lp2_word_lengths() if wb else None

    def kw_for(starts, end=False):
        return {"starts": starts, "end_boundary": end} if wb else {}

    out = []
    for i in range(n_random):
        st = boundaries.sample_starts(rng, length, lengths) if wb else None
        out.append((f"random[{i}]", rng.integers(0, 29, length), kw_for(st)))
    sources = heldout_source(name)
    for i in range(n_heldout):
        runes, ids = sources[int(rng.integers(0, len(sources)))]
        n = min(length, runes.size)
        o = int(rng.integers(0, runes.size - n + 1))
        st = None
        if wb:
            if ids is None:
                st = boundaries.sample_starts(rng, n, lengths)
            else:
                prev = int(ids[o - 1]) if o > 0 else None
                st = boundaries.corpus_starts(ids[o : o + n], prev_word_id=prev)
        out.append((f"heldout[{i}]", runes[o : o + n], kw_for(st)))
    st = boundaries.sample_starts(rng, length, lengths) if wb else None
    out.append(("all-F", np.zeros(length, dtype=np.int64), kw_for(st)))
    st = np.ones(length, dtype=bool) if wb else None
    out.append(("max-key", np.full(length, 28, dtype=np.int64), kw_for(st, wb)))
    return out


def longest_probe_windows(scorer: KNScorer, manifest: dict, arrays: dict) -> list:
    """Per sparse level: layout invariants on the exported arrays and the window of the key
    whose linear probe is the longest (it must equal the manifest's ``max_probe``)."""
    base = scorer.base
    out = []
    off_h = off_s = 0
    for e in manifest["levels"]:
        if e["kind"] != "sparse":
            continue
        m, slots, bits = int(e["n_entries"]), int(e["slots"]), int(e["bits"])
        check(m > 0, f"level {e['level']}: empty sparse level")
        check(slots == 2**bits and slots >= 2 * m, f"level {e['level']}: slots {slots} vs M {m}")
        check(int(e["offset"]) == off_h and int(e["sorted_offset"]) == off_s, "level offsets")
        keys = arrays["sorted_keys"][off_s : off_s + m]
        hk = arrays["hash_keys"][off_h : off_h + slots]
        check(bool(np.all(keys[1:] > keys[:-1])), f"level {e['level']}: keys not ascending")
        filled = np.flatnonzero(hk != EMPTY)
        check(filled.size == m, f"level {e['level']}: {filled.size} filled slots for {m} keys")
        order = np.argsort(hk[filled], kind="stable")
        check(np.array_equal(hk[filled][order], keys), f"level {e['level']}: hash keys differ")
        slot = filled[order]  # the slot of every sorted key
        home = kn_fit.hash_slot0(keys, bits).astype(np.int64)
        probes = ((slot - home) & (slots - 1)) + 1
        check(
            int(probes.max()) == int(e["max_probe"]),
            f"level {e['level']}: longest probe {int(probes.max())} != max_probe {e['max_probe']}",
        )
        for name_, arr in (("lp", "sorted_lp"), ("bow", "sorted_bow")):
            want = arrays[arr][off_s : off_s + m]
            got = arrays[f"hash_{name_}"][off_h : off_h + slots][slot]
            check(np.array_equal(got, want), f"level {e['level']}: hash {name_} differ")
        longest = int(keys[int(np.argmax(probes))])
        ext = _unpack(longest, base, int(e["level"]))
        if scorer.boundary is None:
            out.append((f"longest-probe[level {e['level']}]", np.array(ext), {}))
        else:
            runes, starts, end = _unextend(ext, scorer.boundary)
            if runes.size:
                kw = {"starts": starts, "end_boundary": end}
                out.append((f"longest-probe[level {e['level']}]", runes, kw))
        off_h += slots
        off_s += m
    check(off_h == arrays["hash_keys"].size and off_s == arrays["sorted_keys"].size, "totals")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preset", required=True, help="a KN scorer preset, e.g. kn8-cicada")
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "kn-export")
    ap.add_argument("--L", type=int, default=240, help="window length of the parity windows")
    ap.add_argument("--random", type=int, default=1_000, help="random windows")
    ap.add_argument("--heldout", type=int, default=100, help="held-out windows")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    name = args.preset
    if name not in presets.PRESETS or presets.model_of(name) != "kn":
        kn_names = [n for n in presets.names() if presets.model_of(n) == "kn"]
        raise SystemExit(f"export_kn: {name!r} is not a KN preset; known: {', '.join(kn_names)}")

    t0 = time.time()
    scorer = presets.get(name)
    t_fit = time.time() - t0
    path = args.out / f"{name}.npz"
    t0 = time.time()
    manifest = scorer.export(path)
    t_export = time.time() - t0
    side = path.with_suffix(".json")

    with np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    embedded = json.loads(str(arrays.pop("manifest")))
    check(embedded == manifest, "the manifest inside the npz differs from the returned one")
    check(json.loads(side.read_text(encoding="utf-8")) == manifest, "the side manifest differs")
    check(manifest["version"] == "knx-1" and manifest["numbering"] == "LP2-0-57", "header")
    check(manifest["fingerprint"] == scorer.fingerprint(), "manifest fingerprint")

    t0 = time.time()
    loaded = KNScorer.load_export(path)
    t_load = time.time() - t0
    check(loaded.fingerprint() == scorer.fingerprint(), "reloaded fingerprint differs")

    windows = windows_for(scorer, name, args.L, args.random, args.heldout, args.seed)
    windows += longest_probe_windows(scorer, manifest, arrays)
    t0 = time.time()
    for label, runes, kw in windows:
        want = scorer.logprobs(runes, **kw)
        check(np.array_equal(loaded.logprobs(runes, **kw), want), f"{label}: reloaded logprobs")
        check(
            np.array_equal(loaded.reference_logprobs(runes, **kw), want),
            f"{label}: reference_logprobs over the exported hash",
        )
        check(np.array_equal(scorer.reference_logprobs(runes, **kw), want), f"{label}: reference")
    t_parity = time.time() - t0

    print(f"preset:       {name}  ({scorer!r})")
    print(f"npz:          {path}  {path.stat().st_size:,} bytes")
    print(f"manifest:     {side}  {side.stat().st_size:,} bytes")
    for k, v in arrays.items():
        print(f"  {k:<12} {v.dtype.name:<8} {v.size:>12,} entries  {v.nbytes:>14,} bytes")
    print(f"fingerprint:  {manifest['fingerprint']}")
    print(
        f"parity:       PASS on {len(windows)} windows at L={args.L} ({args.random} random, "
        f"{args.heldout} held-out, all-F, max-key, {len(windows) - args.random - args.heldout - 2}"
        f" longest-probe); fit {t_fit:.1f} s, export {t_export:.1f} s, load {t_load:.2f} s, "
        f"parity {t_parity:.1f} s"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
