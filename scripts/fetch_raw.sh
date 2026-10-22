#!/usr/bin/env bash
# Fetch the five vendored source repos under data/raw/ at their pinned commits.
#
# By default each submodule is a shallow, blobless, sparse checkout of only the files
# runeforge reads (a few MB instead of ~900 MB of page images and archives). Use --full
# for complete shallow checkouts (needed for the Phase 4 image work).
#
#   scripts/fetch_raw.sh          # sparse (what CI uses)
#   scripts/fetch_raw.sh --full   # everything, via git submodule update
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [[ "${1:-}" == "--full" ]]; then
  git submodule update --init --depth 1
  exit 0
fi

sparse_paths() {
  case "$1" in
    rtkd) printf '%s\n' \
      /liber-primus__transcription--master/ /liber-primus__translation/ \
      /liber-primus__keys/ /liber-primus__index/ ;;
    scream314) printf '%s\n' /liber_primus.md /gematria_primus.md /pages_and_ciphers.md /README.md ;;
    cicada_tools) printf '%s\n' '/*.py' '/*.txt' /liber_primus/ /README.md ;;
    dukotah) printf '%s\n' \
      /README.md /liber-primus/PROBLEM.json /liber-primus/LEDGER.json /liber-primus/SOLVED-PAGES.json \
      /liber-primus/ELIMINATION-LEDGER.md /liber-primus/SOLVERS-DOSSIER.md /liber-primus/ARMADA-DOCTRINE.md \
      /liber-primus/handoff/ /liber-primus/benchmark/ /corpus/B-liber-primus/CONFLICTS-B.md \
      /liber-primus/verify_solution.py /liber-primus/src/ /liber-primus/tests/ \
      /liber-primus/analysis/run_stats.py /liber-primus/analysis/round11/lib_numchannel.py \
      /liber-primus/analysis/campaign18_skip/skipdecode.py /liber-primus/analysis/handoff/validate_ledger.py \
      /liber-primus/analysis/round19/G3/gen_py27.py /liber-primus/analysis/round19/G3/validation.json \
      /liber-primus/data/krisyotam_runes.txt /liber-primus/data/english_quadgrams.txt \
      /liber-primus/data/scream314_lp.md \
      /liber-primus/data/keys/self_reliance.txt \
      /liber-primus/data/keys/armada18/emerson_essays_first_series.txt \
      /liber-primus/data/keys/armada18/melville_moby_dick.txt \
      /liber-primus/analysis/latin/latin_218.txt \
      /liber-primus/analysis/round10b/B6-non-english-plaintext/corpora/oe_beowulf.txt ;;
    jens-wedin) printf '%s\n' /README.md /validate_solved.py /src/core/ ;;
    *) echo "unknown source $1" >&2; return 1 ;;
  esac
}

git config -f .gitmodules --get-regexp '^submodule\..*\.path$' | while read -r key path; do
  name="${key#submodule.}"; name="${name%.path}"
  url="$(git config -f .gitmodules --get "submodule.${name}.url")"
  sha="$(git ls-files -s "$path" | awk '{print $2}')"
  base="$(basename "$path")"
  if [[ -e "$path/.git" ]] && [[ "$(git -C "$path" rev-parse HEAD 2>/dev/null)" == "$sha" ]]; then
    echo "ok       $path @ ${sha:0:12}"
    continue
  fi
  echo "fetching $path @ ${sha:0:12} (sparse)"
  rm -rf "$path"
  mkdir -p "$path"
  git -C "$path" init -q
  git -C "$path" remote add origin "$url"
  git -C "$path" config core.sparseCheckout true
  sparse_paths "$base" > "$path/.git/info/sparse-checkout"
  git -C "$path" fetch -q --depth 1 --filter=blob:none origin "$sha"
  git -C "$path" checkout -q --detach FETCH_HEAD
done
