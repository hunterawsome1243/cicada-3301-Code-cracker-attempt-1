"""The lane forward model acts on the canonical runes in every ciphertext view: the
anti-repeat filter suppresses canonical doublets and an interrupter is a canonical F."""

from __future__ import annotations

import numpy as np
import pytest
import yaml

from runeforge import canon
from runeforge.lanes import load_lane
from runeforge.runner import pipeline

VIEWS = ["raw", "atbash", "first-difference", "chain-increment"]


def _lane(tmp_path, **over):
    spec = {
        "lane_id": "MODEL",
        "hypothesis": "forward-model fixture",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 1000],
        "pages": [0, 1],
        "control": {"planted_seed": 1, "synthetic_page": "solved:a-koan-1"},
        **over,
    }
    path = tmp_path / f"{spec['ciphertext_view']}.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return load_lane(path)


def _plain() -> np.ndarray:
    return np.concatenate([s.plain for s in canon.load_solved_sections()])


@pytest.mark.parametrize("view", VIEWS)
def test_the_filter_suppresses_canonical_doublets_in_every_view(tmp_path, view):
    lane = _lane(tmp_path, ciphertext_view=view, filter_model="anti-repeat", interrupt_prob=0.0)
    p = np.tile(_plain(), 3)
    c, _ = pipeline.encrypt(lane, p, pipeline.keys(lane, 5, 3 * p.size), np.random.default_rng(1))
    canonical = pipeline.unview(c, view)
    rate = float((canonical[1:] == canonical[:-1]).mean())
    assert 0.003 < rate < 0.012, rate  # LP2 0.66 %; without the filter 1/29 = 3.4 %


@pytest.mark.parametrize("view", VIEWS)
def test_an_interrupter_is_a_canonical_f_in_every_view(tmp_path, view):
    lane = _lane(tmp_path, ciphertext_view=view, interrupt_prob=1.0)
    p = _plain()
    c, used = pipeline.encrypt(
        lane, p, pipeline.keys(lane, 5, 2 * p.size), np.random.default_rng(1)
    )
    canonical = pipeline.unview(c, view)
    assert np.all(canonical[p == 0] == 0)
    assert used == int((p != 0).sum())  # interrupters do not advance the key


@pytest.mark.parametrize("view", VIEWS)
def test_without_filter_or_interrupts_the_rigid_decode_inverts_it(tmp_path, view):
    lane = _lane(tmp_path, ciphertext_view=view, interrupt_prob=0.0)
    p = _plain()[:500]
    k = pipeline.keys(lane, 9, 500)
    c, used = pipeline.encrypt(lane, p, k, np.random.default_rng(0))
    assert used == 500 and np.array_equal(pipeline.decrypt(lane, c, k), p)
