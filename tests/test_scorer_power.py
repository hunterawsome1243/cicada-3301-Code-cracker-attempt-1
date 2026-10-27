"""The scorer power harness (scripts/scorer_power.py; docs/kn-scorer-design.md section 6).

* ``--smoke`` runs end to end in one process: the JSON holds every section, the rendered
  markdown starts with "not a solve", carries the numbering, the canon SHA-256, the git SHA
  and the scale, and holds none of scripts/check_results.py's banned words; the fit records it
  writes are scale-marked and never installable; nothing under reports/calib-staging, lanes/
  or ledger/ is touched;
* ``--render-only`` re-renders the same markdown from the JSON; ``--section`` merges one
  section into the existing JSON of the same scale;
* the small maths: Wilson intervals, the two-sample KS statistic, the Gumbel bar equal to
  ``calib.threshold_for``'s on an installed record, the banned-word check with its exemptions;
* the families decode their own plants exactly and their wrong keys do not; plant windows
  are deterministic per cell, carry a word-start mask and never cross a section join;
* ``held_out`` tells training text from the 90/10 tail and the excluded solved sections.

Corpus-dependent cases are marked ``raw`` and skip without ``data/corpora``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from runeforge import corpus
from runeforge.paths import REPO_ROOT
from runeforge.scoring import calib

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import scorer_power as sp

SCRIPT = REPO_ROOT / "scripts" / "scorer_power.py"
CANON = "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585"


def _need_corpus(name="cicada-english"):
    if name not in corpus.names():
        pytest.skip(f"corpus {name!r} not built: python scripts/build_corpus.py")


def _snapshot(d: Path) -> dict[str, int]:
    return (
        {p.name: p.stat().st_mtime_ns for p in d.glob("**/*") if p.is_file()} if d.exists() else {}
    )


def _run(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ----------------------------------------------------------------------------- the smoke run


@pytest.fixture(scope="module")
def smoke(tmp_path_factory) -> dict:
    """One ``--smoke`` run per module; the tests below read its outputs."""
    _need_corpus()
    out = tmp_path_factory.mktemp("smoke") / "scorer_power.json"
    before = {
        "staging": _snapshot(sp.STAGING),
        "lanes": _snapshot(REPO_ROOT / "lanes"),
        "ledger": _snapshot(REPO_ROOT / "ledger"),
        "reports_md": (REPO_ROOT / "reports" / "scorer_power.md").exists(),
    }
    t0 = time.time()
    r = _run("--smoke", "--workers", "1", "--out", str(out))
    seconds = time.time() - t0
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    print(f"smoke: {seconds:.1f} s")
    return {"out": out, "md": out.with_suffix(".md"), "before": before, "seconds": seconds}


@pytest.mark.raw
def test_smoke_json_holds_every_section(smoke):
    data = json.loads(smoke["out"].read_text("utf-8"))
    assert list(data["sections"]) == sp.SECTIONS
    for name in sp.SECTIONS:
        assert data["sections"][name] is not None, name
    assert data["not_a_solve"] is True
    assert data["numbering"] == "LP2-0-57"
    assert data["canon_sha256"] == CANON
    assert data["scale"] == "smoke"
    assert data["N_claim"] == 10**6 and data["N_family"] == 2**32 and data["alpha"] == 0.01
    nulls = data["sections"]["nulls"]["cells"]
    assert {(c["scorer"], c["L"]) for c in nulls} == {
        (s, 100) for s in ("lp-ngram3-heldout", "kn4-cicada", "kn8-cicada-wb")
    }
    for c in nulls:
        assert c["null"]["n"] == 2000
        assert set(c["bars"]) == {"claim", "family"}
        assert c["bars"]["claim"]["N"] == 10**6 and c["bars"]["family"]["N"] == 2**32
        assert len(c["wrong_key"]) == len(sp.FAMILIES)
        assert any(not w["in_equality_claim"] for w in c["wrong_key"])  # the Vigenere family
    rows = [r for r in data["sections"]["power"]["rows"] if "claim" in r]
    assert len(rows) == 3 and all(r["n_plants"] == 5 for r in rows)
    for r in rows:
        assert r["held_out"] is True
        assert 0 <= r["claim"]["power"] <= 1 and len(r["claim"]["ci"]) == 2
        assert r["target_line"]
    beam = data["sections"]["beam"]
    assert len(beam["cells"]) == 2 * 4 * 3  # scorers x decoders (rigid too) x forward models
    assert all(c["plant_text"] == sp.SOLVED_REGISTER for c in beam["cells"])
    b = data["sections"]["boundaries"]
    assert b["page_start_masks"]["n_masks"] == 54
    assert b["gain"]["score_boundaries_false"]["measured_once"] is True
    assert data["sections"]["throughput"]["rows"][0]["keys_per_s_L240"] > 0
    assert "reopens_if" in data["sections"]["conditionals"]
    assert data["sections"]["reproduce"]["git_sha"]


@pytest.mark.raw
def test_smoke_markdown_is_a_report(smoke):
    text = smoke["md"].read_text("utf-8")
    lines = text.splitlines()
    assert lines[0] == "not a solve"
    assert lines[2].startswith("# ") and "scorer_power.py" in lines[2]
    assert 'numbering: "LP2-0-57"' in text
    assert CANON in text
    assert "git `" in text and "scale **smoke**" in text
    assert sp.banned_lines(text) == []
    for head in (
        "## 0. Reusable parts",
        "## 1. Not covered",
        "## 2. Nulls and bars",
        "## 3. Power table",
        "## 4. Register confusion matrix",
        "## 5. Beam cells",
        "## 6. Boundaries",
        "## 7. Order and discounts",
        "## 8. Throughput",
        "## 9. The three conditionals and reopens_if",
        "## 10. Reproduce",
    ):
        assert head in text, head
    assert text.index("## 1. Not covered") < text.index("## 2. Nulls")  # negatives first
    for word in ("key space swept", "decoder transition model", "adjudicator register"):
        assert word in text
    assert "reopens_if" in text
    assert text.count("scale smoke") >= 11  # every caption names the scale and N
    assert text.count("N_claim = 10^6, N_family = 2^32") >= 11
    assert "--section nulls" in text  # the regenerating command next to the numbers


@pytest.mark.raw
def test_smoke_writes_scale_marked_fits_and_touches_nothing_frozen(smoke):
    fits = smoke["out"].parent / "fits"
    recs = sorted(fits.glob("*.json"))
    assert recs
    for p in recs:
        rec = json.loads(p.read_text("utf-8"))
        assert rec["scale"] == "smoke" and rec["installable"] is False
        assert rec["preset"] and rec["L"] and rec["scorer_fingerprint"]
        assert set(rec["fit"]) >= {"mu_block", "beta", "block", "n_blocks"}
        assert p.name == calib.path_for(rec["preset"], rec["L"]).name
    before = smoke["before"]
    assert _snapshot(sp.STAGING) == before["staging"]
    assert _snapshot(REPO_ROOT / "lanes") == before["lanes"]
    assert _snapshot(REPO_ROOT / "ledger") == before["ledger"]
    assert (REPO_ROOT / "reports" / "scorer_power.md").exists() == before["reports_md"]


@pytest.mark.raw
def test_render_only_and_section_merge(smoke):
    md = smoke["md"].read_text("utf-8")
    r = _run("--render-only", "--out", str(smoke["out"]))
    assert r.returncode == 0, r.stderr[-2000:]
    assert smoke["md"].read_text("utf-8") == md
    data = json.loads(smoke["out"].read_text("utf-8"))
    r = _run("--smoke", "--section", "reproduce", "--out", str(smoke["out"]))
    assert r.returncode == 0, r.stderr[-2000:]
    merged = json.loads(smoke["out"].read_text("utf-8"))
    assert list(merged["sections"]) == sp.SECTIONS
    assert merged["sections"]["nulls"] == data["sections"]["nulls"]
    assert "--section reproduce" in merged["sections"]["reproduce"]["command"]
    assert smoke["md"].read_text("utf-8").splitlines()[0] == "not a solve"


# ----------------------------------------------------------------------------- the maths


def test_wilson_interval():
    lo, hi = sp.wilson(0, 5)
    assert lo == 0.0 and abs(hi - 0.4345) < 1e-3
    lo, hi = sp.wilson(5, 5)
    assert abs(lo - 0.5655) < 1e-3 and hi == 1.0
    lo, hi = sp.wilson(50, 100)
    assert abs(lo - 0.4038) < 1e-3 and abs(hi - 0.5962) < 1e-3
    assert all(np.isnan(sp.wilson(0, 0)))


def test_ks_statistic():
    a = np.arange(10, dtype=float)
    assert sp.ks_stat(a, a) == 0.0
    assert sp.ks_stat(a, a + 100) == 1.0
    assert abs(sp.ks_stat(np.array([0.0, 1.0]), np.array([0.0, 1.0, 2.0, 3.0])) - 0.5) < 1e-12
    assert abs(sp.ks_crit(1000, 1000) - 1.358 * np.sqrt(2 / 1000)) < 1e-12


def test_the_gumbel_bar_is_threshold_fors():
    rec = calib.load("lp-ngram3-heldout:rigid", 240)
    t = calib.threshold_for(10**6, "lp-ngram3-heldout:rigid", 240)
    assert abs(sp.bar_at(rec["fit"]["mu_block"], rec["fit"]["beta"], 10**6) - t.bar) < 1e-12
    t32 = calib.threshold_for(2**32, "lp-ngram3-heldout:rigid", 240)
    assert abs(sp.bar_at(rec["fit"]["mu_block"], rec["fit"]["beta"], 2**32) - t32.bar) < 1e-12


def test_fit_scores_reports_bars_intervals_and_the_check():
    rng = np.random.default_rng(0)
    scores = rng.gumbel(-7.0, 0.1, 50_000)
    fit = sp.fit_scores(scores, 50_000, np.random.default_rng(1))
    assert fit["fit"]["n_blocks"] == 50 and fit["fit"]["block"] == 1000
    for key in ("claim", "family"):
        b = fit["bars"][key]
        assert b["ci"][0] <= b["bar"] <= b["ci"][1] and b["bootstrap"] == 200
    assert fit["bars"]["family"]["bar"] > fit["bars"]["claim"]["bar"] > fit["null"]["max"] - 1.0
    assert fit["check"]["max_error"] < 0.1  # 25,000-draw block maxima where the fit predicts


def test_banned_words_are_caught_with_check_results_exemptions():
    assert (
        sp.banned_lines("the nine solved sections\nheldout-solved-sections\nlanes/x/solved.md")
        == []
    )
    w1, w2, w3 = "clo" + "sed", "sol" + "ved", "confir" + "med"  # never written out in full
    bad = sp.banned_lines(f"ok\nthis family is {w1} and {w2}\n{w3}")
    assert [b.split(":")[0] for b in bad] == ["line 2", "line 2", "line 3"]
    assert f"'{w1}'" in bad[0] and f"'{w2}'" in bad[1] and f"'{w3}'" in bad[2]


def test_scales_follow_the_design():
    q, f, s = sp.SCALES["reduced"], sp.SCALES["full"], sp.SCALES["smoke"]
    assert (q.draws, q.plants, q.beam_plants, q.beam_decoys, q.beam_draws, q.wb_masks) == (
        100_000,
        200,
        50,
        99,
        25_000,
        2_000,
    )
    assert (f.draws, f.plants, f.beam_plants) == (1_000_000, 1_000, 200) and f.stage
    assert not q.stage and not s.stage
    assert q.lengths == [100, 240, 250, 263, 500, 1000] and len(q.scorers) == 13
    assert q.registers == sp.REGISTERS and len(q.registers) == 6
    assert (len(s.registers), s.lengths, len(s.scorers), s.draws, s.plants) == (
        1,
        [100],
        3,
        2000,
        5,
    )
    assert q.kill_seconds == 12 * 60


# ----------------------------------------------------------------------------- families, plants


@pytest.mark.parametrize("fam", sp.FAMILIES, ids=[f.name for f in sp.FAMILIES])
def test_every_family_decodes_its_own_plant_and_not_a_wrong_key(fam):
    rng = np.random.default_rng(7)
    plain = rng.integers(0, 29, 60)
    lane = sp.fam_lane(fam, 60)
    cipher, key = sp.fam_encrypt(fam, lane, plain, rng)
    assert cipher.shape == plain.shape
    assert np.array_equal(sp.fam_decrypt(fam, lane, cipher, key), plain)
    wrong = sp.fam_wrong_decodes(fam, lane, cipher, key, 8, rng)
    assert wrong.shape == (8, 60)
    assert not any(np.array_equal(w, plain) for w in wrong)


def test_the_toy_lane_is_in_memory_and_rigid():
    lane = sp.toy_lane(100)
    assert lane.lane_id == "SCORER-POWER" and lane.window == 100
    assert lane.interrupt_prob == 0.0 and lane.filter_model == "off"
    assert lane.decoder_problems() == []
    beam = sp.toy_lane(120, preset="kn4-cicada:beam", **sp.MODELS["anti-repeat"])
    assert beam.decoder_problems()  # a pairing the lane spec refuses is still measured


@pytest.mark.raw
def test_plant_windows_are_deterministic_masked_and_never_cross_a_join():
    _need_corpus()
    a = sp.plant_windows("cicada-english", 240, 6, 0)
    b = sp.plant_windows("cicada-english", 240, 6, 0)
    assert np.array_equal(a["plains"], b["plains"]) and np.array_equal(a["offsets"], b["offsets"])
    assert a["starts"].dtype == bool and a["starts"].shape == (6, 240)
    assert not np.array_equal(a["plains"], sp.plant_windows("cicada-english", 240, 6, 1)["plains"])
    runes, starts, segs = sp.register_text(sp.SOLVED_REGISTER)
    assert runes.size == 1533 and len(segs) == 2 and starts[0] and starts[778]
    w = sp.plant_windows(sp.SOLVED_REGISTER, 500, 40, 3)
    for off in w["offsets"]:
        assert any(a0 <= off and off + 500 <= b0 for a0, b0 in segs)
    with pytest.raises(ValueError):
        sp.plant_windows(sp.SOLVED_REGISTER, 1000, 1, 0)


@pytest.mark.raw
def test_held_out_tells_training_text_from_the_tail():
    _need_corpus()
    assert sp.held_out("kn4-cicada", "cicada-english")  # the 90/10 tail
    assert not sp.held_out("cicada-ngram3", "cicada-english")  # no split: training text
    assert sp.held_out("kn8-general", "vowel-dropped-english")  # derived family, same tail
    assert not sp.held_out("general-ngram3", "vowel-dropped-english")
    assert sp.held_out("kn8-latin", "english-general")
    assert sp.held_out("lp-ngram3-heldout", sp.SOLVED_REGISTER)
    assert sp.held_out("kn4-lp-heldout", sp.SOLVED_REGISTER)
    assert not sp.held_out("lp-ngram3", sp.SOLVED_REGISTER)
    assert sp.held_out("kn8-cicada", sp.SOLVED_REGISTER)


# ------------------------------------------------------------------ review fixes (2026-10-27)


def test_finite_families_are_outside_the_claim_and_enumerate_their_wrong_keys():
    by = {f.name: f for f in sp.FAMILIES}
    assert not by["vigenere-short-key"].in_equality_claim
    assert not by["atbash-shift"].in_equality_claim and by["atbash-shift"].n_keys == 58
    assert not by["totient-stream"].in_equality_claim and by["totient-stream"].n_keys == 10_000
    assert all(f.in_equality_claim and f.n_keys is None for f in sp.FAMILIES if f.kind == "lane")
    rng = np.random.default_rng(3)
    plain = rng.integers(0, 29, 80)
    cipher, key = sp.fam_encrypt(by["atbash-shift"], None, plain, rng)
    wrong = sp.fam_wrong_decodes(by["atbash-shift"], None, cipher, key, 5000, rng)
    assert wrong.shape == (57, 80) and len({w.tobytes() for w in wrong}) == 57
    assert not any(np.array_equal(w, plain) for w in wrong)
    cipher, key = sp.fam_encrypt(by["totient-stream"], None, plain, rng)
    wrong = sp.fam_wrong_decodes(by["totient-stream"], None, cipher, key, 300, rng)
    assert wrong.shape == (300, 80) and len({w.tobytes() for w in wrong}) == 300


@pytest.mark.raw
def test_wrong_key_decodes_are_cached_int8_and_scorer_independent():
    _need_corpus("english-general")
    sp.wrong_key_decodes.cache_clear()
    a, starts = sp.wrong_key_decodes(1, 60, 100, "english-general")
    b, _ = sp.wrong_key_decodes(1, 60, 100, "english-general")
    assert a is b and a.dtype == np.int8 and a.shape == (57, 60) and starts.shape == (60,)
    assert sp.wrong_key_decodes.cache_info().hits >= 1


@pytest.mark.raw
def test_plant_windows_draw_distinct_offsets_and_report_the_overlap():
    _need_corpus()
    w = sp.plant_windows(sp.SOLVED_REGISTER, 500, 200, 0)
    assert w["plains"].shape == (200, 500) and len(set(w["offsets"].tolist())) == 200
    assert (
        w["n_offsets"] == 535 and w["n_disjoint"] == 2
    )  # 279 + 256 offsets; 778 // 500 + 755 // 500
    capped = sp.plant_windows(sp.SOLVED_REGISTER, 500, 1000, 0)
    assert capped["plains"].shape == (535, 500) and len(set(capped["offsets"].tolist())) == 535
    w = sp.plant_windows(sp.SOLVED_REGISTER, 263, 200, 0)
    assert w["n_offsets"] == 1009 and w["n_disjoint"] == 4
    w = sp.plant_windows("cicada-english", 240, 200, 0)
    assert len(set(w["offsets"].tolist())) == 200 and w["n_disjoint"] >= 100


def test_not_covered_is_computed_after_the_measured_sections_and_names_the_overlap():
    assert sp.COMPUTE_ORDER.index("not_covered") > sp.COMPUTE_ORDER.index("power")
    assert sp.COMPUTE_ORDER.index("conditionals") > sp.COMPUTE_ORDER.index("power")
    assert sp.COMPUTE_ORDER[-1] == "reproduce" and sorted(sp.COMPUTE_ORDER) == sorted(sp.SECTIONS)
    assert sp.SECTIONS.index("not_covered") == 1  # the rendered order stays negatives-first
    cfg = sp.SCALES["reduced"]
    fresh = sp.section_not_covered(cfg, {"power": None})
    assert not any("training text" in x for x in fresh)
    power = {
        "rows": [{"scorer": "cicada-ngram3", "register": "cicada-english", "held_out": False}],
        "cells": [
            {
                "register": sp.SOLVED_REGISTER,
                "L": 500,
                "n_plants": 200,
                "n_offsets": 535,
                "n_disjoint": 2,
            },
            {  # a corpus tail at L = 100: 307 disjoint windows >= 200 plants, no line
                "register": "cicada-english",
                "L": 100,
                "n_plants": 200,
                "n_offsets": 30890,
                "n_disjoint": 307,
            },
        ],
    }
    lines = sp.section_not_covered(cfg, {"power": power})
    assert any(
        x.startswith("cicada-ngram3 x cicada-english: plant text is training text") for x in lines
    )
    overlap = [x for x in lines if "windows can be disjoint" in x]
    assert len(overlap) == 1 and overlap[0].startswith(
        f"{sp.SOLVED_REGISTER} at L = 500: 200 plants"
    )
    assert "535" in overlap[0] and "only 2 windows" in overlap[0]
    assert any("atbash-shift, totient-stream are outside" in x for x in lines)


def test_fit_record_states_the_null_sample_it_reports():
    rng = np.random.default_rng(0)
    scores = rng.gumbel(-7.0, 0.1, 20_000)
    fit = sp.fit_scores(scores, 20_000, np.random.default_rng(1))

    class _S:
        def fingerprint(self):
            return "f" * 64

    rec = sp.fit_record(_S(), "x", "rigid", 100, fit, "reduced", {})
    assert rec["draws"] == 20_000 and rec["null"]["n"] == 20_000
    assert (
        rec["null"]["mean"] == float(scores.mean())
        and "every one of the 20,000 draws" in rec["method"]
    )


def test_captions_carry_numbering_canon_git_scale_and_n():
    cap = sp._cap({"sections": {}, "scale": "smoke", "git_sha": "abc1234567890def"}, "k", "nulls")
    assert cap.startswith(
        "*numbering LP2-0-57 · canon `023312066df4…` · git `abc123456789` · scale smoke"
    )
    assert "N_claim = 10^6, N_family = 2^32, alpha = 0.01" in cap and "JSON `k`" in cap
    assert "--section nulls" in cap


@pytest.mark.raw
def test_smoke_report_captions_and_commands_carry_provenance(smoke):
    text = smoke["md"].read_text("utf-8")
    assert text.count("*numbering LP2-0-57 · canon `023312066df4…` · git `") >= 11
    data = json.loads(smoke["out"].read_text("utf-8"))
    cmds = data["sections"]["reproduce"]["section_commands"]
    # the run's own --out is carried so a one-section rerun merges into this JSON (an earlier
    # test re-ran --section reproduce without --workers, so only --out is pinned here)
    assert all(f"--out {smoke['out']}" in c for c in cmds.values())
    # the wrong-key table of section 2 is an nb cell; the wb cell's table sits in section 6
    i2, i3, i6, i7 = (text.index(h) for h in ("## 2.", "## 3.", "## 6.", "## 7."))
    assert "cells[scorer=lp-ngram3-heldout, L=100].wrong_key" in text[i2:i3] or (
        "cells[scorer=kn4-cicada, L=100].wrong_key" in text[i2:i3]
    )
    assert "cells[scorer=kn8-cicada-wb, L=100].wrong_key" not in text[i2:i3]
    assert "cells[scorer=kn8-cicada-wb, L=100].wrong_key" in text[i6:i7]
    cells = {c["scorer"]: c for c in data["sections"]["nulls"]["cells"]}
    wb = cells["kn8-cicada-wb"]
    assert (
        all(not w["in_equality_claim"] for w in wb["wrong_key"])
        and wb["ks_max_in_claim"] != wb["ks_max_in_claim"]
    )
    atbash = next(w for w in cells["kn4-cicada"]["wrong_key"] if w["family"] == "atbash-shift")
    assert (
        atbash["n"] == 57 and atbash["n_keys"] == 58 and atbash["above_bar_at_n_keys"] is not None
    )
    assert not atbash["in_equality_claim"]
    lane = next(w for w in cells["kn4-cicada"]["wrong_key"] if w["family"].startswith("sha256"))
    assert (
        lane["in_equality_claim"] and lane["n_keys"] is None and lane["above_bar_at_n_keys"] is None
    )
    assert "disjoint" not in "\n".join(data["sections"]["not_covered"])  # one register, 30k tail


def test_a_banned_word_keeps_the_json_and_leaves_no_stale_markdown(tmp_path, monkeypatch):
    out = tmp_path / "r.json"
    out.write_text('{"scale": "OLD"}', encoding="utf-8")
    out.with_suffix(".md").write_text("OLD MD", encoding="utf-8")
    monkeypatch.setattr(sp, "render", lambda data: "line one\nthis page is " + "sol" + "ved\n")
    with pytest.raises(SystemExit, match="not written"):
        sp.write_outputs({"scale": "NEW"}, out)
    assert json.loads(out.read_text("utf-8")) == {"scale": "NEW"}
    assert not out.with_suffix(".md").exists()
    monkeypatch.setattr(sp, "render", lambda data: "clean\n")
    assert sp.write_outputs({"scale": "NEW"}, out).read_text("utf-8") == "clean\n"


def test_beam_rigid_rows_reuse_the_nulls_cell_at_a_shared_length(tmp_path):
    """One rigid bar per (scorer, L) in a report: section_beam takes the nulls section's cell
    for the rigid decoder where it exists and fits its own only where it does not."""
    import dataclasses

    cfg = dataclasses.replace(
        sp.SCALES["smoke"], beam_scorers=["lp-ngram3-heldout"], beam_lengths=[120], beam_plants=2,
        beam_decoys=3, beam_draws=2_000,
    )  # fmt: skip
    fake_fit = sp.fit_scores(
        np.random.default_rng(0).gumbel(-7.0, 0.1, 25_000), 25_000, np.random.default_rng(1)
    )
    cell = {
        "scorer": "lp-ngram3-heldout", "L": 120, "draws": 25_000, **fake_fit,
        "scale_check": {"source": "installed", "file": "x", "delta_bar_claim": 0.0},
        "fit_record": ["fits/x.json"],
    }  # fmt: skip
    beam = sp.section_beam(cfg, 1, tmp_path, {"cells": [cell]})
    rigid = [n for n in beam["nulls"] if n["decoder"] == "rigid"]
    assert len(rigid) == 1 and rigid[0]["draws"] == 25_000
    assert rigid[0]["bars"] == fake_fit["bars"] and "reused" in rigid[0]["null_source"]
    assert rigid[0]["scale_check"]["source"] == "installed"
    assert all(
        n["draws"] == 2_000 and "beam_calib" in n["null_source"]
        for n in beam["nulls"]
        if n["decoder"] != "rigid"
    )
    cell_rigid = [c for c in beam["cells"] if c["decoder"] == "rigid"]
    assert cell_rigid and all(
        c["claim"]["bar"] == fake_fit["bars"]["claim"]["bar"] for c in cell_rigid
    )


def test_scale_check_lengths_add_installed_records_only():
    q, f, s = sp.SCALES["reduced"], sp.SCALES["full"], sp.SCALES["smoke"]
    assert q.scale_check_lengths == [120] and f.scale_check_lengths == [120]
    assert s.scale_check_lengths == []
    for name in ("cicada-ngram3", "general-ngram3", "lp-ngram3-heldout"):
        assert sp._has_record(f"{name}:rigid", 120) and sp._has_record(f"{name}:rigid", 240)
    assert not sp._has_record("kn4-cicada:rigid", 120)
