#!/usr/bin/env bash
# PreToolUse hook for the verify-lane subagent (.claude/agents/verify-lane.md frontmatter):
# its Bash may run only `python ...` (SESSION_PROMPT.md section C4, docs/BOOTSTRAP_CHECKLIST.md:
# "Read and Bash(python *) only"). A `tools:` specifier does not narrow Bash, so this hook does.
# One command, starting with python/python3, and no shell operator, redirection or
# substitution outside single quotes (code inside `python -c '...'` is fine). Exit 2 blocks
# the call (stderr goes to the subagent); exit 0 allows it. It filters command text, not what
# Python then does; the subagent's own rules forbid writing in the repository.
# Note: hooks in a project agent's frontmatter run only once the workspace is trusted.
exec python3 -I -c '
import json, re, sys

def unquoted_operator(cmd):
    quote = None
    for ch in cmd:
        if quote == "\x27":
            if ch == "\x27":
                quote = None
            continue
        if quote == "\x22":
            if ch == "\x22":
                quote = None
            elif ch in "`$":
                return ch
            continue
        if ch in "\x27\x22":
            quote = ch
        elif ch in ";&|<>()`$\n":
            return ch
    return "unbalanced quote" if quote else None

try:
    cmd = ((json.load(sys.stdin).get("tool_input") or {}).get("command") or "").strip()
except ValueError:
    sys.exit(0)
bad = None if re.match(r"python3?(?:\.\d+)?(?:\s|$)", cmd) else "not a python command"
bad = bad or unquoted_operator(cmd)
if bad:
    print(f"verify-lane may run only one `python ...` command ({bad!r}); use "
          "`python -m runeforge.cli ...` for the CLI and single quotes around -c code",
          file=sys.stderr)
    sys.exit(2)
'
