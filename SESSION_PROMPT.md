# SESSION_PROMPT.md — the runeforge improvement loop (one lane per interactive session)

<!-- Hunter pastes this at the start of every interactive Claude Code session, or types /session
     once it is installed as .claude/skills/session/SKILL.md. CLAUDE.md is already loaded; this file
     is the procedure. Phase 1–2 sessions use §B; everything after uses §C. One lane per session.
     ultrathink is allowed on step 3 only (lane choice); nowhere else. -->

You are running one iteration of the runeforge improvement loop. The goal of this session is
**one finished lane with an honest ledger row**, or one finished instrument task, and then a stop at
the human checkpoint. Not two lanes. Not "while I'm here". If the lane finishes early, write the row,
commit, and stop; the next session picks the next lane with fresh context.

## A. Boot (every session; do not skip, do not reorder)

1. `git status && git log --oneline -15` — a dirty tree means the last session ended badly. Read the
   last commit message and `PICKUP-HERE.md`. If a lane folder has a PREREG but no RESULTS, that lane is
   the only candidate for this session (finish it or park it with cause; never silently abandon it).
2. Trust anchor, in this order, and paste the last line of each into your first message:
   `pytest -q -m "not slow"` · `runeforge canon --verify` · `python -m runeforge.oracle --selftest`.
   Any failure → this session is a repair session. Fix only the failure, re-run, commit
   `fix(trust-anchor): …`, stop. No attack work on a red anchor.
3. `runeforge status --short` (open lanes, running jobs, last 5 rows) and `cat PICKUP-HERE.md`.
   Each job is listed from its `runs/<id>/status.json`; status marks it ALIVE only when the PID's
   cmdline is a runeforge sweep with the recorded start time. A dead job that is not `done` with
   a `running` row is itself a finding: set the row to `parked` with `parked_state` = the checkpoint
   cursor, and say so.
4. `python scripts/validate_ledger.py` must print `Unsound negatives = 0`. If it does not, repairing the
   ledger is this session's lane (it is a red-team lane: verdict FOUND-ERROR, with `supersedes` links).
5. Read `queue.json` (the round plan Hunter approved) and the `Rejections` section of
   `PICKUP-HERE.md` first — a rejected verify, a failed control, or a NOISE-CROSSER from the last session
   is the first thing you must know, not the last.

## B. Build sessions (Phase 1–2, while the spec's "definition of done" for the phase is unmet)

- Pick the next unmet item in the spec's §6 "definition of done" for the current phase, in order.
  Implement it test-first: write the failing test from the spec's exact numbers (nine solved sections,
  magic squares 1033/3301, prime sentence sums, 86 doublets, IoC 1.000, entropy 4.857), then the code.
- The phase's deliverables become part of the frozen toolbox the moment their tests go green: add the
  paths to `FROZEN.txt` in the same commit. From then on, changing them is a `TOOLBOX_REQUESTS.md` entry.
- Phase 2 ends with `reports/scorer_power.md` — the power table (English, Latin, vowel-dropped English,
  Cicada register × page lengths 100/250/500/1000/full) **measured by planting the correct key**, never
  by reasoning about the design. If Latin power is ≈ 0, that is a result to publish, not to hide, and it
  becomes the standing conditional on every later negative.
- Show evidence, not assertions: paste the pytest summary line and the benchmark number, with the command.

## C. Lane sessions (Phase 3 onward)

### C1. Choose the lane (budget discipline)
Compute the round's spend so far from the ledger (`runeforge status --round`) and pick the category that
is furthest below its share: ≈ 30 % instrument (power envelopes, null recalibration, beam/scorer work,
the clock-variant scorer the murphy campaign left unbuilt) · 40 % high-prior bounded lanes (the Py2.7-MT
`exact` lane parked at 44.14 %, the unswept 32-bit generators, derived-key B-04/B-05, keyed-increment
chain, the P-8 doublet-site audit) · 20 % red-team of **this project's own** claims (re-derive a headline
number with independently written code; pair each load-bearing sentence in README/ledger with
Claim (file:line) → Actual evidence → Overreach → Live lane it hides → Cheapest settling test) ·
10 % closeout (finished compute with no write-up is the cheapest open item in any ledger; file it).
Rank inside a category by Dukotah R5: finite checkable object > enumerable generator space > instrument
audit > samplable space with stated fraction > unbounded. A lane whose Q2 fact is "it feels like 3301"
is a completeness ritual and queues last. Say in one line which category and why, with the percentages.

### C2. Pre-register (frozen before any measurement)
Create `lanes/<id>/PREREG.md` from `.claude/rules/lanes.md` and commit it (`lane(<id>): PREREG frozen`)
**before** running anything in this lane. It contains:
- Header: date, "written before any measurement in this lane", what was read (file paths), and
  "no decode, plant, null or sweep of this lane's own has been executed at the time of writing".
- Aiming Test Q1–Q5 (Q2 with a file path; Q5 is the kill condition at 10 % of budget, as a number).
- Hypothesis: one falsifiable sentence. Key space and size. Ciphertext view (raw / Atbash / chain /
  first-difference). Decoder: the preset's (`rigid`, or the beam decoder matching the lane's filter
  and interrupt model: `beam`, `beam-skip`, `beam-skip-int`; width and max_skip are pinned per decoder
  name). A rigid screen cannot see a filtered key (control 0/20), so a filtered lane decodes with the
  beam in its control, null and sweep alike. Scorer register(s).
- Positive control, pre-specified: the planted key in the real shape (seed inside the real generator, at
  a random offset, on synthetic Cicada-register English), the numeric pass bar (rune-index recovery
  ≥ 0.90 on ≥ 90 % of ≥ 20 plants; planted score above the bar; a deliberately wrong key below the
  noise ceiling). A control that can only pass is decoration.
- Null: size-matched shuffle of the real runes, n ≥ 200, AND the domain-separated SHA-256 stream null;
  report `null_mean`, `null_sd`, `null_max`. Threshold = `scripts/threshold_for.py --n <true N> --preset
  <decoder> --L <segment>` (small N: `max(floor, null_max + 0.5)`). Expected false positives over the
  slice, written as a number, < 1.
- Hit function (ALL of): bar clear at the lane's true N · rune-index self-consistency ≥ 0.90 on held-out
  halves · improves when the window doubles (head → page → full stream) · oracle PASS. Score alone is never
  a hit. Decision rule: `NULL` / `FLAGGED-FOR-ORACLE` (never auto-certified) / `INCONCLUSIVE (power)`.
- Verdict arithmetic (jens-wedin's floor/ceiling, written now, rendered by `runeforge control`, never by
  hand): detection floor = the minimum score of the planted hypotheses that self-recover through this
  pipeline; matched ceiling = a null with the same length, the same number of trials and the same scorer,
  drawn from a source outside every family this lane searches. `INCONCLUSIVE (power)` if fewer than half
  of the planted hypotheses are individually identifiable, or if floor − ceiling < 0.25 nats (the search
  cannot separate a real key from noise at any score; inspect decodes, not numbers). Best real ≥ floor →
  crosser protocol. Otherwise `NULL`, stated as "best real X vs floor Y vs ceiling Z".
- Budget: wall-clock, decode count, GPU-hours (> 2 GPU-hours needs Hunter's approval in `queue.json`).
- What this lane will NOT do (`not_covered`, declared now so the negative cannot expand its own scope),
  the three conditionals, `reopens_if`, `external_ids` (Dukotah / jens / Leo / murphy ids this maps to).

### C3. Gate, then control, then run
1. **Gate** (`runeforge gate lanes/<id>.yaml`): simulate the hypothesised cipher on Cicada-register
   English with ≥ 12 random keys; if most keys fail a hard constraint of the LP2 fingerprint (C1 IoC,
   C2 doublet rate, C2b conditional IoC, C2c doublet positions mod 2..8, C3 repeated words, C6
   cross-word doublets; murphy's rule -- C5 lag-5 and C4 word-length layout are reported, not
   deciding), the gate prints `GATE FAIL` and the verdict is `EXCLUDED (gate)`: write RESULTS.md, file
   the row, stop. A gate FAIL excludes the typical key, not the family — say so in `not_covered`.
2. **Control** (`runeforge control lanes/<id>.yaml`): the planted positive through the exact pipeline.
   Pass bar not met → the lane is `INCONCLUSIVE (power)`. Fix the instrument *as a new instrument lane*
   or park with cause. Do not lower the bar. Do not search.
3. **Run**: CPU screen first (≤ 30 min). GPU sweeps launch detached (`runeforge sweep … --detach`) and
   write `runs/<id>/status.json` every chunk; poll with `cat`, never block on them. Check the Q5 kill
   condition at 10 % of budget and write the check into RESULTS.md whether or not it fired. Every
   trial, including crashes, gets a SWEEPROW line with its reproduce command.
4. **Crosser**: any score above the pre-registered bar → HIT_PROTOCOL.md, immediately, before anything
   else in this session. Do not stop the sweep. Do not announce. Do not write "hit" anywhere but the
   protocol's own log until the protocol says `hit-verified`.

### C4. Results, mechanical check, independent re-derivation
- Write `lanes/<id>/RESULTS.md` in the template: 0 headline numbers · 1 why this lane · 2 instrument
  audited before the sweep (trust anchor output, control numbers) · 3 result vs null vs bar, with
  `null_mean/sd/max`, best score, z · 4 survivors reported not dropped, with the escalation table ·
  5 **Coverage — read this, not the verdict** (what was measured; `not_covered` restated with numbers;
  the three conditionals) · 6 what would change this verdict (`reopens_if`) · 7 artifacts and the exact
  reproduce command. `Verdict:` line first word from the vocabulary in CLAUDE.md.
- `python scripts/check_results.py lanes/<id>/RESULTS.md` must print PASS (sections present; control
  states recovered k/n at rank 1; null states n ≥ 20 with mean/sd/max; a z-score; a vocabulary verdict;
  CANDIDATE only with an oracle line). FAIL means the lane is not finished.
- Spawn the `verify-lane` subagent (`.claude/agents/verify-lane.md`: fresh context, `Read` + `Bash(python *)`,
  may not import lane code) with: "Re-derive the headline numbers in lanes/<id>/RESULTS.md from
  `runs/<id>/sweep.jsonl` and `data/canon/` with your own code. Replay the control on a fresh seed. Report
  one line per number: reproduced / differs (give the number to trust and whether the verdict changes) /
  not checked. Flag only differences that change the verdict." A `differs` that changes the verdict →
  the lane is not finished; record it under `Rejections` in PICKUP-HERE.md so the next session boots on it.

### C5. Ledger, docs, commit, stop
- `runeforge ledger update <id>` with status, threshold, `threshold_fixed_in_advance: true`,
  `positive_control`, `control_detail`, `null`, `result`, `coverage`, `not_covered`, `conditionals`,
  `evidence[]` (paths that exist), `reproduce`, `reopens_if`, `external_ids`, `data_sha256`, `git_sha`.
  Then `python scripts/validate_ledger.py`. Corrections to older rows go through `supersedes`.
- Update `PICKUP-HERE.md` (one-paragraph state of the board; what this session shipped; open lanes
  ranked; rejections; do-not-re-run with the row id). Keep superseded text under a dated banner; never delete.
- Commit `lane(<id>): <VERDICT> — <one line>`. Then print the checkpoint block and **stop**:

```
=== CHECKPOINT ===
lane:        <id>  (<category>; round split now I/B/R/C = __/__/__/__ %)
verdict:     <NULL | CANDIDATE | INCONCLUSIVE (power) | EXCLUDED (gate) | FOUND-ERROR | NO-ERROR-FOUND>
control:     recovered k/n at rank 1; planted <score> vs bar <bar>; wrong key <score>
null:        n=<n> mean=<m> sd=<s> max=<max>; threshold_for(N=<N>) = <bar>
best real:   <score> (z = <z>); escalation head/page/full = <a>/<b>/<c>
coverage:    <what was swept>     not_covered: <what was not>
conditionals: key space <…> | decoder <…> | register <…>
reopens_if:  <condition>
verify-lane: reproduced <k>/<n> numbers; differs: <none | list>
running jobs: <none | id pid cursor eta>
needs Hunter: <nothing | approval for … | TOOLBOX_REQUESTS entry | LEAD.md>
next lane (suggested, not started): <id> because <one line>
=== END ===
```

## D. Rules that hold in every step
- One variable at a time. Small runs are for finding bugs, never for conclusions.
- Do not re-run measured ground; cite the row (`B-02`, `N23`, murphy lane `W`) you would be duplicating.
- Evidence, not assertions: every number in RESULTS.md has a command that regenerates it.
- Read logs with `grep`/`tail -n 20`; never flood the context with a sweep log.
- If you have corrected the same mistake twice in this session, stop, write what you learned into
  `PICKUP-HERE.md` under `Lessons`, and end the session; the next one starts clean.
- You are not allowed to decide the plaintext is English. If you catch yourself reading a decode and
  forming an opinion, write the decode's rune indices to the crosser log and run the protocol instead.
