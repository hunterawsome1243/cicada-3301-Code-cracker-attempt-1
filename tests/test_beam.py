"""The beam interrupt decoder (runeforge.beam; spec section 2.4 and Phase 2 deliverable P2).

* given only the key, it re-derives the published interrupt sets of the three keyed solved
  sections (WELCOME 11 of 25, A KOAN 2 2 of 5, AN END 1 of 5) and their plaintext, with
  scorers that never saw Liber Primus text;
* it recovers a planted DIVINITY key on a synthetic Welcome page the rigid decoder rejects;
* the batched numpy decoder and the scalar reference agree path for path, in every view and
  combine, with skips on; a row decodes the same alone or in any batch;
* through ``pipeline.decrypt`` the frozen control passes lanes the rigid decoder fails: an
  interrupt-only lane under ``:beam``, an anti-repeat lane (the family that passes the
  fingerprint gate) under ``:beam-skip``, both together under ``:beam-skip-int``;
* crosser step 6 replays the sweep's decode record and catches an edited one.
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pytest
import yaml

from runeforge import beam, canon, interrupts
from runeforge.lanes import LaneSpec, load_lane
from runeforge.runner import control, crosser, pipeline, sweep
from runeforge.scoring import presets
from runeforge.transforms import Vigenere, from_method

DIVINITY = [23, 10, 1, 10, 9, 10, 16, 26]  # WELCOME's key, DIUINITY
KEYED = ("welcome", "a-koan-2", "an-end")


def _section(sid):
    return next(s for s in canon.load_solved_sections() if s.id == sid)


def _lane(**over) -> LaneSpec:
    spec = {
        "lane_id": "BEAM-TOY",
        "hypothesis": "toy beam lane (test fixture)",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 2**32],
        "window": 240,
        "pages": [0, 1, 2, 3, 4, 5],
        "preset": "lp-ngram3-heldout:beam-skip-int",
        "filter_model": "anti-repeat",
        "interrupt_prob": 1.0,
        "control": {"planted_seed": 3301, "synthetic_page": "solved:a-koan-1", "decoys": 199},
    }
    spec.update(over)
    return LaneSpec(**spec)


# ----------------------------------------------------------------------------- solved pages


@pytest.mark.raw  # the corpus scorers train on data/corpora, built from data/raw
@pytest.mark.parametrize("scorer", ["general-ngram3", "cicada-ngram3"])
@pytest.mark.parametrize("sid", KEYED)
def test_the_beam_rederives_the_solved_interrupt_sets_from_the_key_alone(scorer, sid):
    s = _section(sid)
    plain, chosen = interrupts.decode_beam(s.cipher, from_method(s.method), presets.get(scorer))
    assert chosen == sorted(s.interrupts)
    assert np.array_equal(plain, s.plain)


@pytest.mark.parametrize("sid", KEYED)
def test_decode_beam_round_trips_through_skip_known(sid):
    """Mechanics with the always-available scorer (trained on these pages, so this is not a
    power claim: the test above is)."""
    s = _section(sid)
    t = from_method(s.method)
    plain, chosen = interrupts.decode_beam(s.cipher, t, presets.get("lp-ngram3"), width=4)
    assert np.array_equal(interrupts.decode_skip_known(s.cipher, t, chosen), plain)
    assert np.array_equal(plain, s.plain)
    first = min(chosen)  # the rigid decode agrees up to the first interrupter
    assert np.array_equal(interrupts.decode_rigid(s.cipher, t)[:first], s.plain[:first])


def test_decode_beam_needs_a_keystream_transform():
    s = _section("a-koan-1")
    with pytest.raises(TypeError, match="keystream transform"):
        interrupts.decode_beam(s.cipher, from_method(s.method), presets.get("lp-ngram3"))


def test_a_planted_divinity_key_the_rigid_decoder_rejects():
    """Spec P2: a synthetic Welcome page -- held-out Cicada-register text of WELCOME's length
    enciphered with DIVINITY under the interrupt rule (every plaintext F an interrupter) -- is
    recovered by the beam and rejected by the rigid decoder (CLAUDE.md: -6.835 rigid vs
    -4.170 beam under Dukotah's scorer)."""
    scorer = presets.get("lp-ngram3-heldout")
    text = canon.solved_section("a-koan-1").plain[:515]  # held out of this scorer
    chosen = np.flatnonzero(text == interrupts.F).tolist()
    assert len(chosen) == 8 and chosen[0] == 53
    t = Vigenere(DIVINITY)
    cipher = interrupts.encrypt_with_interrupts(text, t, chosen)
    rigid = interrupts.decode_rigid(cipher, t)
    plain, got = interrupts.decode_beam(cipher, t, scorer)
    assert got == chosen and np.array_equal(plain, text)
    s_rigid, s_beam = scorer.score(rigid), scorer.score(plain)
    assert (rigid == text).mean() < 0.2  # out of step after the first interrupter
    assert s_rigid < -6.5 and s_beam > -4.5 and s_beam - s_rigid > 2.5


# ----------------------------------------------------------------------------- parity


CASES = list(itertools.product(beam.VIEWS, beam.COMBINES))


@pytest.mark.parametrize("view,combine", CASES)
def test_batched_decoder_matches_the_reference(view, combine):
    scorer = presets.get("lp-ngram3-heldout")
    src = canon.solved_section("a-koan-1").plain
    rng = np.random.default_rng(CASES.index((view, combine)))  # fixed per case
    lane = _lane(ciphertext_view=view, combine=combine, window=120)
    model = beam.BeamModel(combine=combine, view=view, width=6, p_keep=0.19, max_skip=2)
    for _ in range(2):
        off = int(rng.integers(0, src.size - 120))
        k = rng.integers(0, 29, 400)
        mc, _ = pipeline.encrypt(lane, src[off : off + 120], k, rng)
        keys = np.stack([k[:120], *rng.integers(0, 29, (3, 120))])
        res = beam.decode_batch(mc, keys, scorer, model)
        for row in range(keys.shape[0]):
            ref = beam.decode_reference(mc, keys[row], scorer, model)
            assert ref.plain == res.plain[row].tolist()
            assert ref.objective == res.objective[row]
            got = beam.record_from(res, row, model)
            assert (got.interrupts, got.skips, got.fill) == (ref.interrupts, ref.skips, ref.fill)


def test_a_row_decodes_the_same_alone_or_in_any_batch():
    scorer = presets.get("lp-ngram3-heldout")
    model = presets.beam_model("beam-skip-int")
    rng = np.random.default_rng(7)
    c = rng.integers(0, 29, 200)
    keys = rng.integers(0, 29, (37, 200))
    whole = beam.decode(c, keys, scorer, model)
    assert np.array_equal(beam.decode(c, keys, scorer, model, max_rows=5), whole)
    assert np.array_equal(beam.decode(c, keys[11], scorer, model), whole[11])


def test_the_key_budget_is_the_keys_given():
    scorer = presets.get("lp-ngram3-heldout")
    model = presets.beam_model("beam-skip-int")
    c = np.zeros(50, dtype=np.int64)
    with pytest.raises(ValueError, match=">= 50 key symbols"):
        beam.decode_batch(c, np.zeros((1, 49), dtype=np.int64), scorer, model)
    res = beam.decode_batch(c, np.zeros((1, 50), dtype=np.int64), scorer, model)
    assert res.keys_used[0] <= 50


def test_the_decoder_parameters_are_pinned_to_their_names():
    """Calibrations and control evidence were measured with exactly these; a change is a new
    decoder name, never an edit."""
    assert presets.DECODERS == ("rigid", "beam", "beam-skip", "beam-skip-int")
    assert presets.DECODER_PARAMS == {
        "rigid": {},
        "beam": {"width": 8, "interrupt_prob": 15 / 16, "p_keep": None, "max_skip": 0},
        "beam-skip": {"width": 8, "interrupt_prob": 0.0, "p_keep": 0.19, "max_skip": 6},
        "beam-skip-int": {"width": 8, "interrupt_prob": 15 / 16, "p_keep": 0.19, "max_skip": 6},
    }
    assert presets.split_preset("lp-ngram3:beam-skip") == ("lp-ngram3", "beam-skip")
    with pytest.raises(KeyError):
        presets.split_preset("lp-ngram3:beam-wide")


def test_pipeline_decrypt_dispatches_on_the_preset():
    rng = np.random.default_rng(1)
    c, k = rng.integers(0, 29, 120), rng.integers(0, 29, (4, 120))
    rigid = _lane(preset="lp-ngram3-heldout:rigid", window=120)
    assert np.array_equal(pipeline.decrypt(rigid, c, k), pipeline.rigid_decrypt(rigid, c, k))
    lane = _lane(window=120)
    want = beam.decode(c, k, presets.get("lp-ngram3-heldout"), pipeline.beam_model(lane))
    assert np.array_equal(pipeline.decrypt(lane, c[None, :], k), want)
    assert pipeline.decrypt(lane, c, k[0]).shape == (120,)


# ----------------------------------------------------------------------------- controls


def test_an_interrupt_lane_passes_its_control_under_beam_and_not_rigid():
    rigid = control.run_control(_lane(filter_model="off", preset="lp-ngram3-heldout:rigid"))
    assert rigid.status == "failed" and rigid.identified < 18
    rep = control.run_control(_lane(filter_model="off", preset="lp-ngram3-heldout:beam"))
    assert rep.status == "passed", rep.reasons
    assert rep.identified == rep.n_plants and rep.gap_nats > 0.25


def test_the_gate_passing_family_passes_its_control_under_beam_skip():
    """Anti-repeat filter, no interrupters: the template lane's family under the gate."""
    lane = _lane(interrupt_prob=0.0, preset="lp-ngram3-heldout:beam-skip")
    rigid = control.run_control(lane.model_copy(update={"preset": "lp-ngram3-heldout:rigid"}))
    assert rigid.status == "failed" and rigid.identified == 0
    rep = control.run_control(lane)
    assert rep.status == "passed", rep.reasons
    assert rep.identified >= 18 and rep.gap_nats > 0.25


def test_an_anti_repeat_interrupt_lane_passes_under_beam_skip_int_only():
    for dec in ("rigid", "beam"):
        rep = control.run_control(_lane(preset=f"lp-ngram3-heldout:{dec}"))
        assert rep.status == "failed" and rep.identified == 0, dec
    rep = control.run_control(_lane())
    assert rep.status == "passed", rep.reasons
    assert rep.identified >= 18 and rep.gap_nats > 0.25


# ----------------------------------------------------------------------------- crossers


def _pending(tmp_path, lane: LaneSpec, seed: int, record: dict | None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    lane_yaml = tmp_path / f"{lane.lane_id}.yaml"
    lane_yaml.write_text(yaml.safe_dump(lane.model_dump(mode="json")), encoding="utf-8")
    base = tmp_path / "runs"
    pend = base / lane.lane_id / "crossers" / f"{lane.lane_id}-{seed}.pending"
    pend.parent.mkdir(parents=True)
    rec = {
        "kid": f"{lane.lane_id}-{seed}",
        "status": "FLAGGED-FOR-ORACLE",
        "lane_path": str(lane_yaml),
        "seed": seed,
        "score": 0.0,
        "window": lane.window,
        "preset": lane.preset,
        "decode_record": record,
    }
    pend.write_text(json.dumps(rec), encoding="utf-8")
    return base, rec["kid"]


def test_step6_replays_the_sweeps_decode_record_and_catches_an_edit(tmp_path):
    lane = _lane(pages=[0], window=120)
    record = sweep.crosser_decode_record(lane, 5)
    assert record["key_budget"] == sweep.record_budget(pipeline.lane_cipher(lane).size)
    assert record["fill"] == []
    base, kid = _pending(tmp_path, lane, 5, record)
    res = crosser.reencipher(kid, base=base)
    assert res["verdict"] == "passes step 6" and res["mismatches"] == 0
    # an edited plaintext no longer re-enciphers to the canonical runes
    bad = dict(record, plain=[(x + 1) % 29 if i == 3 else x for i, x in enumerate(record["plain"])])
    base2, kid2 = _pending(tmp_path / "b", lane, 5, bad)
    assert crosser.reencipher(kid2, base=base2)["verdict"] == "NOISE-CROSSER"
    # a record with fill positions is INCOMPLETE, never a pass
    base3, kid3 = _pending(tmp_path / "c", lane, 5, dict(record, fill=[7]))
    assert crosser.reencipher(kid3, base=base3)["verdict"] == "INCOMPLETE"


def test_record_violations_flags_steps_the_forward_model_cannot_take():
    lane = _lane(ciphertext_view="raw", combine="vigenere")
    # plaintext [7, 7]: canonical rune 0 is 7 + 5 = 12; at position 1 key 5 would repeat 12
    p, k = np.array([7, 7]), np.array([5, 5, 9])
    assert crosser.record_violations(lane, p, k, skips={1: 1}) == []
    assert crosser.record_violations(lane, p, np.array([5, 6, 9]), skips={1: 1})
    assert crosser.record_violations(lane, np.array([3, 1]), k, interrupts=[0])
    assert crosser.record_violations(lane, p, k, skips={0: 1})


def test_escalation_uses_the_beams_own_null(tmp_path):
    lane = _lane(pages=[0, 1], window=120, preset="lp-ngram3-heldout:beam")
    base, kid = _pending(tmp_path, lane, 9, None)
    esc = crosser.escalate(kid, base=base, n_null=40)
    first = esc["rows"][0]
    # a wrong key under the beam scores like the beam's null, not far above a uniform null
    assert abs(first["z"]) < 4
    assert first["null_mean"] > -7.0  # above the rigid uniform-string null mean (~ -7.17)


def test_load_lane_accepts_the_beam_presets(tmp_path):
    path = tmp_path / "l.yaml"
    path.write_text(yaml.safe_dump(_lane().model_dump(mode="json")), encoding="utf-8")
    assert load_lane(path).preset == "lp-ngram3-heldout:beam-skip-int"


# ----------------------------------------------------------------------------- calibration


def test_beam_calibration_draws_are_fixed_per_chunk():
    """Each chunk draws from default_rng([seed, chunk]), so the scores do not depend on how
    many worker processes ran them."""
    from runeforge.scoring import beam_calib

    job = ("lp-ngram3-heldout", "beam-skip", 60, 3301, 4, 40, None)
    a, b = beam_calib._chunk(job), beam_calib._chunk(job)
    assert np.array_equal(a, b) and a.shape == (40,)
    assert not np.array_equal(
        a, beam_calib._chunk(("lp-ngram3-heldout", "beam-skip", 60, 3301, 5, 40, None))
    )
    with pytest.raises(ValueError, match="rigid decoder"):
        beam_calib.measure("lp-ngram3-heldout", "rigid", 60, draws=25_000)
    with pytest.raises(ValueError, match="multiple"):
        beam_calib.measure("lp-ngram3-heldout", "beam", 60, draws=1_000)


def test_a_beam_null_sits_above_the_rigid_null():
    """Why the beam needs its own bars: the best path through a wrong key beats a uniform
    string."""
    from runeforge.scoring import beam_calib

    scorer = presets.get("lp-ngram3-heldout")
    rng = np.random.default_rng(0)
    rigid = scorer.score_batch(rng.integers(0, 29, (400, 120))).mean()
    for dec in ("beam", "beam-skip", "beam-skip-int"):
        s = beam_calib._chunk(("lp-ngram3-heldout", dec, 120, 3301, 0, 400, None))
        assert s.mean() > rigid + 0.1, dec


def test_an_interrupt_decoders_null_rises_with_the_canonical_f_count():
    """Why interrupt-decoder bars are fitted at the most F-rich window's count: under ``beam``
    a wrong key's best path climbs with the number of canonical F's; under ``beam-skip`` it
    does not depend on the cipher."""
    from runeforge.scoring import beam_calib

    def block_max(dec, n_f):
        s = beam_calib._chunk(("lp-ngram3-heldout", dec, 240, 7, 0, 1000, n_f))
        return s.max(), s.mean()

    lo, hi = block_max("beam", 4), block_max("beam", 20)
    assert hi[1] > lo[1] + 0.2 and hi[0] > lo[0]
    flat = [block_max("beam-skip", n)[1] for n in (4, 20)]
    assert abs(flat[0] - flat[1]) < 0.02


def test_calibration_ciphers_hold_exactly_the_conditioned_f_count():
    from runeforge.scoring import beam_calib

    c = beam_calib._cipher(np.random.default_rng(1), 50, 240, 14)
    assert ((c == 0).sum(axis=1) == 14).all() and c.min() >= 0 and c.max() <= 28
    assert beam_calib.canonical_f(240) == 14 and beam_calib.canonical_f(120) == 10
    assert not beam_calib.uses_interrupts("beam-skip")
    assert beam_calib.uses_interrupts("beam") and beam_calib.uses_interrupts("beam-skip-int")


def _install(monkeypatch, tmp_path, preset, length, **over):
    """A stand-in calibration file in a temporary calibration directory."""
    from runeforge.scoring import beam_calib, calib

    monkeypatch.setattr(calib, "CALIB_DIR", tmp_path)
    scorer, decoder = presets.split_preset(preset)
    rec = {
        "preset": preset,
        "decoder": decoder,
        "L": length,
        "decoder_params": presets.DECODER_PARAMS[decoder],
        "beam_sha256": beam_calib.beam_sha256(),
        "canonical_F": (
            beam_calib.canonical_f(length) if beam_calib.uses_interrupts(decoder) else None
        ),
        "scorer_fingerprint": presets.get(scorer).fingerprint(),
        "fit": {"block": 1000, "mu_block": -6.4, "beta": 0.04},
    }
    rec.update(over)
    calib.path_for(preset, length).write_text(json.dumps(rec), encoding="utf-8")


def test_a_beam_calibration_must_match_the_decoder_and_the_window(monkeypatch, tmp_path):
    from runeforge.scoring import beam_calib

    preset, n_f = "lp-ngram3-heldout:beam", beam_calib.canonical_f(240)
    window = np.zeros(240, dtype=np.int64)
    window[n_f:] = 5  # exactly n_f canonical F's
    _install(monkeypatch, tmp_path, preset, 240)
    assert beam_calib.calibration_problems(preset, 240, window) == []
    window[n_f] = 0  # one F more than the fit covers
    assert any("more than" in p for p in beam_calib.calibration_problems(preset, 240, window))
    _install(monkeypatch, tmp_path, preset, 240, beam_sha256="0" * 64)
    assert any(
        "another runeforge/beam.py" in p
        for p in beam_calib.calibration_problems(preset, 240, window[:0])
    )
    _install(monkeypatch, tmp_path, preset, 240, decoder_params={"width": 4})
    assert any(
        "decoder parameters" in p for p in beam_calib.calibration_problems(preset, 240, window[:0])
    )
    _install(monkeypatch, tmp_path, preset, 240, canonical_F=None)
    assert any(
        "not conditioned" in p for p in beam_calib.calibration_problems(preset, 240, window[:0])
    )
    assert beam_calib.calibration_problems("lp-ngram3-heldout:rigid", 240, window) == []


def test_a_lane_on_an_f_rich_window_is_not_runnable(monkeypatch, tmp_path):
    """Page 11's first 240 runes hold 14 canonical F's (the most of any page-start window); a
    calibration conditioned on fewer must not give it a bar."""
    from runeforge.scoring import calib

    preset = "lp-ngram3-heldout:beam-skip-int"
    _install(monkeypatch, tmp_path, preset, 240, canonical_F=10)
    bar = calib.threshold_for(2**32, preset, 240).bar
    lane = _lane(pages=[11, 12, 13], claim_bar=bar - 0.3, family_wise_bar=bar)
    assert any("canonical F's" in p for p in lane.runnable_problems())
    _install(monkeypatch, tmp_path, preset, 240)
    assert lane.runnable_problems() == []


# ----------------------------------------------------------------------------- model fidelity


@pytest.mark.parametrize("view,combine", CASES)
@pytest.mark.parametrize("decoder,interrupt_prob", [("beam-skip-int", 1.0), ("beam-skip", 0.0)])
def test_the_beam_inverts_the_forward_model(view, combine, decoder, interrupt_prob):
    """Plant with pipeline.encrypt (anti-repeat filter, and interrupters when the lane has
    them) and decode with the true key: the plaintext comes back (a stray rune where two paths
    fit the cipher equally well), and the record is a path the forward model can take that
    re-enciphers to the cipher. Independent of decode_reference, which shares the helpers."""
    scorer = presets.get("lp-ngram3-heldout")
    src = canon.solved_section("a-koan-1").plain
    lane = _lane(ciphertext_view=view, combine=combine, interrupt_prob=interrupt_prob)
    model = presets.beam_model(decoder, combine, view)
    rng = np.random.default_rng(100 + CASES.index((view, combine)))
    recoveries = []
    for _ in range(3):
        off = int(rng.integers(0, src.size - 240))
        plain = src[off : off + 240]
        k = rng.integers(0, 29, 600)
        mc, _used = pipeline.encrypt(lane, plain, k, rng)
        rec = beam.decode_record(mc, k[:300], scorer, model)  # budget past the skips: no fill
        assert rec.fill == []
        assert crosser.record_violations(lane, rec.plain, k, rec.interrupts, rec.skips) == []
        fwd = crosser.reencipher_forward(lane, rec.plain, k, rec.interrupts, rec.skips)
        assert np.array_equal(fwd, mc)
        recoveries.append((np.asarray(rec.plain) == plain).mean())
    assert min(recoveries) >= 0.95 and np.mean(recoveries) >= 0.98, recoveries


def test_more_than_two_drops_at_one_rune_are_followed():
    """pipeline.encrypt drops any number of key symbols at a rune; at max_skip 2 a run of 3
    or 4 put the beam out of step for up to ~170 runes (adversarial review). The presets now
    follow up to 6."""
    scorer = presets.get("lp-ngram3-heldout")
    lane = _lane(p_keep=0.0, interrupt_prob=0.0)  # forward model: every repeat is dropped
    plain = canon.solved_section("a-koan-1").plain[50:290]
    model = presets.beam_model("beam-skip")
    for n_drop in (3, 4, 5):
        rng = np.random.default_rng(n_drop)
        k = rng.integers(0, 29, 600)
        # make the key drop n_drop symbols at rune 60: each would re-encipher it to a repeat
        prev = int(pipeline.unview(pipeline.encrypt(lane, plain[:60], k, rng)[0], "raw")[-1])
        used = pipeline.encrypt(lane, plain[:60], k, rng)[1]
        rep = (prev - int(plain[60])) % 29  # vigenere: x + k = prev
        k = np.concatenate([k[:used], np.full(n_drop, rep), k[used:]])
        mc, _ = pipeline.encrypt(lane, plain, k, rng)
        rec = beam.decode_record(mc, k[:300], scorer, model)
        assert rec.skips.get(60) == n_drop
        assert (np.asarray(rec.plain) == plain).mean() >= 0.98


def test_priors_that_kill_every_path_are_refused():
    with pytest.raises(ValueError, match="interrupt_prob"):
        beam.BeamModel(interrupt_prob=1.0)
    with pytest.raises(ValueError, match="p_keep"):
        beam.BeamModel(p_keep=0.0)
    s = _section("welcome")
    with pytest.raises(ValueError, match="interrupt_prob"):
        interrupts.decode_beam(
            s.cipher, from_method(s.method), presets.get("lp-ngram3"), interrupt_prob=1.0
        )


def test_a_refit_scorer_is_never_decoded_with_its_old_tables():
    from runeforge.scoring.ngram import NGramScorer

    a = NGramScorer(3).fit([canon.solved_section("welcome").plain])
    c, k = np.arange(60) % 29, np.zeros(60, dtype=np.int64)
    model = presets.beam_model("beam")
    first = beam.decode_batch(c, k, a, model).objective[0]
    a.fit([canon.solved_section("a-koan-1").plain])
    again = beam.decode_batch(c, k, a, model).objective[0]
    fresh = beam.decode_batch(
        c, k, NGramScorer(3).fit([canon.solved_section("a-koan-1").plain]), model
    )
    assert again == fresh.objective[0] and again != first


def test_step6_refuses_steps_the_lanes_hypothesis_rules_out():
    p, k = np.array([7, 7]), np.array([5, 5, 9])
    no_filter = _lane(filter_model="off")
    assert crosser.record_violations(no_filter, p, k, skips={1: 1})
    no_int = _lane(interrupt_prob=0.0)
    assert crosser.record_violations(no_int, np.array([0, 3]), np.array([5, 9, 9]), interrupts=[0])
