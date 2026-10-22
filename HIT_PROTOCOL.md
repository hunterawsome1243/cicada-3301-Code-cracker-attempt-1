# HIT_PROTOCOL.md — what to do when something scores above the claim bar

<!-- Load with /hit, or whenever a sweep writes runs/<id>/crossers/<kid>.pending. This procedure is the
     only path from "a number above the bar" to the word "lead". Every step writes to
     runs/<id>/crossers/<kid>.md as it goes, so a session that dies mid-protocol can be resumed. -->

## 0. Stance

A score above the bar is, with overwhelming probability, the top order statistic of a large sweep. A
1e6-trial α = 0.01 bar applied to a 4.3e9-seed lane expects tens of noise crossers; Dukotah's seed
35563892 crossed at 7.6707 against a 7.3835 bar and was NOISE. Everything here is written to be run by
someone who expects noise, while being ready for the one time it is not. **The sweep is not stopped.
Nobody is told. No file outside `runs/<id>/crossers/` says "hit" until step 8 passes.**

Vocabulary: a crosser is `FLAGGED-FOR-ORACLE` from the moment it crosses; it becomes exactly one of
`PARITY-FAIL`, `NOISE-CROSSER`, or `hit-verified`. There is no "probable", "promising" or "partial".

## 1. Freeze the candidate (before touching anything else)

- Copy the SWEEPROW line verbatim to `runs/<id>/crossers/<kid>.md`: key identity (`kid`), generator,
  seed/params, ciphertext view, filter model, decoder preset, window, score, the lane's bar at its
  true N, and the git SHA + data SHA-256 of the run. Compute and record the candidate's own fingerprint
  (SHA-256 of the regenerated keystream's first 12,956 symbols).
- The candidate is now frozen: no re-tuning of the key, the interrupt set, the window or the register
  is permitted during adjudication. A candidate that only clears after adjustment is a different
  candidate and goes back into the sweep as such.

## 2. Re-derive independently (parity)

- Regenerate the keystream from the frozen key identity with the **CPU reference** implementation
  (`runeforge crosser replay <kid> --cpu`), never the kernel that found it. Decode and score with the
  same preset. Record both numbers. `|Δ| > 1e-6` on the score or any mismatch in the keystream →
  `PARITY-FAIL`: this is an instrument bug, which is itself the finding; open an instrument lane,
  file the crosser as PARITY-FAIL, continue the sweep.
- Then a second re-derivation by the `verify-lane` subagent with its own code (no lane imports),
  reporting reproduced / differs. A `differs` that changes which side of the bar the score lands is
  PARITY-FAIL.

## 3. Double the window (the single most diagnostic step)

- Re-score the frozen candidate at 2× the window, then on the full page, then on the full 12,956-rune
  stream, with the same key continuing (no re-synchronisation, no new interrupts beyond what the beam
  decoder itself chooses). Record the escalation table: head → 2× → page → stream, each with the
  score, the z against a size-matched null of the same length, and the rune-index self-consistency.
- Decision: **a true key gains evidence with length; noise regresses toward the null mean.** A crosser
  whose z falls at any escalation step is a `NOISE-CROSSER`. Do not rescue it with a different
  interrupt set, a different register, or a shorter window.
- Remember that self-consistency of a deterministic decode is 1.0 for noise too; it carries no
  language evidence on its own. The language evidence is the panel score and the non-English
  register panel (persisted language-agnostic stats): a decode whose best register is not English must
  be adjudicated under that register's own null, not waved through because it "scores".

## 4. Held-out and second page

- Split the page into halves; the key frozen in step 1 must clear the bar on each half independently
  (held-out 3/4 recovery ≥ 0.90 under the same key).
- Decode a **second page** with the same mechanism and key continuation. The oracle's own criterion is
  "more than one page independently": a key tuned to one page's statistics is the single most common
  failure mode. Fewer than two pages → `NOISE-CROSSER` (and, if the single-page evidence survived
  steps 2–3 intact, note it in `reopens_if` for the lane; it is not a lead).

## 5. Oracle (ours, then the community's)

- `python -m runeforge.oracle --key-module runs/<id>/crossers/<kid>_key.py` (the module exposes
  `keystream(n) -> list[int]` and records *how* the key was made). The oracle re-decodes all solved
  pages under the same code path first; if that regression fails, the rig is broken and the verdict
  is void.
- `python data/raw/dukotah/liber-primus/verify_solution.py --selftest` then
  `--key-module … --pages 10 --json runs/<id>/crossers/<kid>_oracle.json`. Their PASS requires the
  English band on more than one page independently, a stated margin over a size-matched shuffle null,
  and consistency under both rigid and skip-aware decoders with the stated mechanism. Paste the JSON
  verdict into the crosser log. FAIL → `NOISE-CROSSER` with the criterion it missed and by how much.

## 6. Re-encipher rune for rune

- Take the recovered plaintext and the compact key description (generator, seed, schedule, filter
  model, interrupt positions) and **encrypt forward**. The output must equal the canonical ciphertext
  for every rune of every claimed page, byte for byte (`runeforge crosser reencipher <kid>`).
  Encryption is the deterministic direction (ᚠ is ambiguous on decode, not on encode) and this is the
  test that a plaintext-only "solve" cannot pass. Any mismatch → `NOISE-CROSSER`.
- Save the forward-encryption script and its SHA-256 next to the key module. A claim is the key module
  plus this script, never the plaintext.

## 7. Read it last, and only now

- Only after steps 1–6 pass, open the plaintext. The question is not "does it look English" (a flat
  29-symbol cipher emits THE, YOUR, THING, DIES at the rate any random stream does); the question is
  whether it reads as **continuous prose in the voice of the solved pages across whole pages**, with
  the authors' spelling (BOOC, CNOW, YOV), and whether its own GP-sums and structure behave like the
  solved pages'. Write what you see in two sentences; do not quote fragments as evidence.
- If you are an unattended session: write `PENDING-ADJUDICATION.md` after step 6 instead of reading,
  and stop. A human reads first.

## 8. Only now: LEAD.md and tell Hunter

- Write `LEAD.md` at the repo root with: the frozen key identity and fingerprint; the reproduce
  commands for steps 2–6 and their outputs; the escalation table; both oracle JSON verdicts; the
  forward-encryption script hash; pages decoded; the three conditionals; the lane's PREREG path and its
  frozen bar; and what has **not** been checked. Set the ledger row to `hit-verified`, commit
  `lane(<id>): hit-verified — LEAD.md`, and stop at the checkpoint with `needs Hunter: LEAD.md`.
- Hunter, not Claude, decides what happens next. A `hit-verified` row is "worth a human's time". It is
  not a solve until another party reproduces it from the key module.

## 9. If it is noise (the usual case)

- Write the crosser file with the full escalation table and the step that failed, add one line to the
  lane's RESULTS.md §4 ("survivors reported, not dropped"), and let the sweep continue. Tens of these
  per large lane are expected and are part of the published negative. Never delete a crosser log.

## 10. Community acceptance bar and how to post (Hunter's call, never Claude's)

What the rigorous repositories and the CicadaSolvers norms require before a claim is taken seriously:
(1) the method reproduces every solved page from the canonical runes; (2) a planted key of the same
family is recovered by the same pipeline; (3) whole pages, ≥ 2 independently, under rigid and
skip-aware decoders consistent with the stated mechanism; (4) a trial-count-corrected null is beaten by
a stated margin and the text reads as prose on inspection; (5) the key and method are stated so that
**another party re-runs them to the same plaintext** from a clean checkout. "A solve is accepted by the
community, not by a script." Anything purporting to come from Cicada itself is verified only by PGP key
7A35090F; unsigned "complete translations" are rejected on sight.

Posting, for a lead or for a negative:
- Re-check every claim against the live ledgers (ours, Dukotah's `LEDGER.json`) before posting; the
  ledger moves faster than drafts.
- Lead with what is reusable (the canonical dataset hash, the validator, the scorer power table, the
  decoder), then "what I re-ran and got nothing from, so you don't have to", each with its reproduce
  command; then the one thing you found. Title = the warning or the tool, not a verdict. First line of
  a negative: "not a solve". Partial coverage is stated as partial. Include the "do not recook" list and
  what a legitimate re-run would need.
- For a lead: publish the key module, the forward-encryption script, both oracle JSONs and the clean-
  checkout reproduce command; invite refutation explicitly; say what was not checked. Expect and welcome
  "poke holes in it". Post under Hunter's own name, in a deliberately humble, negative-results-first
  tone; the audience is expert and rightly allergic to overclaiming.
- Where: a GitHub issue or PR on `Dukotah/cicada3301` with a ledger-shaped fragment (`id, lane,
  hypothesis, status, threshold, threshold_fixed_in_advance, positive_control, control_detail, null,
  result, coverage, not_covered, evidence, reproduce, reopens_if`) that `validate_ledger.py` accepts, a
  short post in the CicadaSolvers Discord's relevant channel, and a note that cites Dukotah by round
  and lane file (e.g. "Round 12 front D3") rather than the repo as a whole. The one outside PR there
  has waited four weeks unreviewed, so keep the canonical copy in this repo and cross-link by id.
- Never claim an LLM solved anything. The claim is the key module and the forward encryption; who
  wrote the code is a footnote.
