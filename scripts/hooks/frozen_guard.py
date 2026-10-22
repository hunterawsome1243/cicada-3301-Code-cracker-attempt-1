#!/usr/bin/env python3
"""PreToolUse guard for the frozen toolbox (CLAUDE.md, Frozen toolbox; FROZEN.txt).

Advisory text does not stop an unattended session from "just fixing" the oracle or a test, so
OVERNIGHT_LOOP.md Part 1 §6 makes the freeze a hook: deterministic, and it fires in every
permission mode. ``deny_frozen.sh`` runs this file with ``python3 -I`` before every tool call. It
reads the hook payload on stdin and exits 2 (stderr is shown to Claude) when the call would WRITE
a path listed in FROZEN.txt. Reading a frozen file is always fine.

- Edit / Write / MultiEdit / NotebookEdit: the file path, resolved against the payload ``cwd``
  and checked both as written and with symlinks resolved. Paths outside the project are allowed.
- Bash: the command is tokenised with ``shlex`` after a quote-aware pass that removes comments
  and heredoc bodies and lifts out ``$(...)``, backtick and ``<(...)`` substitutions. Then each
  simple command is read for what it writes: redirections, tee, sed/perl/ruby/awk in-place,
  mv/cp/install/ln, rm/rmdir, chmod/chown, touch/truncate/mkdir, dd of=, git
  checkout/restore/rm/mv, find -delete/-exec, xargs, ``bash -c``/eval, and any statement of
  ``-c``/``-e``/heredoc interpreter code that names a frozen path and writes. ``cd``/``pushd``
  change the base for later relative paths in a chain (not across a pipe or out of a subshell);
  ``$VAR`` is expanded from the environment and earlier assignments in the same command. A write
  whose target cannot be read off the command (``rm $(...)``, ``xargs rm``) is blocked when the
  command names a frozen path anywhere; a command shlex cannot tokenise is blocked when it names
  a frozen path next to any write operator or command word.

It is a guard against accidents and casual workarounds, not a sandbox. Not covered: a script or
program that writes a frozen file from its own code (``python scripts/calibrate.py`` included),
patches applied from a diff (``patch < x.diff``, ``git apply``), and tree-wide git moves (branch
switches, ``git reset --hard``, ``git stash``); git history and CI are the backstop there. It
must be fast and must never wedge a session, so it uses the standard library only, starts no
subprocess, and allows the call with a warning on an unreadable payload, a missing FROZEN.txt or
an internal error (a Bash command then gets the conservative check).
"""

from __future__ import annotations

import fnmatch
import glob
import json
import os
import re
import shlex
import sys

REASON = (
    "frozen: {} is listed in FROZEN.txt; write the change request to TOOLBOX_REQUESTS.md "
    "instead (CLAUDE.md, Frozen toolbox)"
)
SCRIPT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
WRITEISH_TOOL = re.compile(r"write|edit", re.I)  # e.g. an MCP write_file tool with a file_path
MAX_DEPTH = 6  # nesting of bash -c / eval / $(...) before falling back to the literal check

# --- shell lexing -------------------------------------------------------------------------------
PUNCT = "();<>|&\n"  # shlex punctuation; quoted or escaped copies are swapped for private-use chars
PLACE = {ch: chr(0xE000 + k) for k, ch in enumerate(PUNCT)}
UNPLACE = {ord(v): k for k, v in PLACE.items()}
MARK, MARK_END = "", ""  # a lifted $(...) / `...` / <(...) substitution: MARK<n>MARK_END
MARK_RE = re.compile(MARK + r"(\d+)" + MARK_END)
OPS_RE = re.compile(r"&>>|&>|>>|>\||>&|<>|<<<|<<|<&|&&|\|\||\|&|;;|[;&|()\n<>]")
SEPARATORS = frozenset({";", "&&", "||", "|", "|&", "&", ";;", "\n", "(", ")"})
WRITE_REDIRS = frozenset({">", ">>", ">|", "&>", "&>>", "<>", ">&"})
HEREDOC_RE = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([^\s;&|<>()'\"`]+))")
ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*\+?=")
VAR_RE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
BRACE_RE = re.compile(r"\{[^{}]*(?:,|\.\.)[^{}]*\}")
GLOB_CHARS = frozenset("*?[")

# --- what writes --------------------------------------------------------------------------------
KEYWORDS = frozenset({"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!"})
KEYWORDS |= {"{", "}"}
WRAPPERS = {  # command prefixes -> their options that take a separate value
    "sudo": {"-u", "-g", "-C", "-D", "-p", "-r", "-t", "-U", "-h"},
    "doas": {"-u", "-C"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
    "nice": {"-n", "--adjustment"},
    "nohup": set(),
    "command": set(),
    "builtin": set(),
    "exec": {"-a"},
    "time": {"-f", "-o", "--format", "--output"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
    "setsid": set(),
    "ionice": {"-c", "-n", "-p", "-P", "-u"},
    "watch": {"-n", "--interval"},
    "xargs": {"-I", "-L", "-n", "-P", "-d", "-E", "-s", "-a", "--arg-file", "--delimiter"},
}
SIMPLE_WRITERS = {  # every positional argument is written; value -> options taking a value
    "rmdir": set(),
    "unlink": set(),
    "shred": {"-n", "-s", "--iterations", "--size"},
    "touch": {"-r", "-d", "-t"},
    "truncate": {"-s", "-r"},
    "tee": set(),
    "mkdir": {"-m", "--mode"},
    "mkfifo": {"-m", "--mode"},
}
COMPRESSORS = frozenset({"gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz", "zstd", "unzstd"})
FORMATTERS = frozenset({"black", "isort"})  # and `ruff format` / `ruff check --fix`
FORMATTER_VALUED = {"-l", "--line-length", "-t", "--target-version", "--config", "--select"}
FORMATTER_VALUED |= {"--ignore", "--exclude", "--extend-exclude", "--include", "-o", "-W"}
SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
INTERP_RE = re.compile(r"^(?:python[\d.]*|perl|ruby|node)$")
CODE_WRITE_RE = re.compile(  # interpreter code that writes (only matters if it names a frozen path)
    r"""['"](?:[wax]|[rwax]\+|[wax]b|[rwax]b\+|[rwax]\+b|[wax]t)['"]"""  # open() write modes
    r"""|['"]\s*\+?>{1,2}"""  # perl/shell-style ">file"
    r"""|\b(?:write_text|write_bytes|unlink|rmtree|removedirs|makedirs|chmod|chown|sysopen"""
    r"""|symlink_to|hardlink_to|writeFileSync|writeFile|appendFileSync|appendFile|rmSync"""
    r"""|unlinkSync|renameSync)\b"""
    r"""|\bos\.(?:remove|rename|replace|truncate|mkdir|symlink|link)\b|\bshutil\.\w+"""
    r"""|\.(?:touch|rename|replace|mkdir|truncate)\("""
)
WRITE_HINT_RE = re.compile(  # the conservative check for a command that does not tokenise
    r">|--in-place|(?<![\w./-])(?:rm|rmdir|mv|cp|install|ln|chmod|chown|chgrp|touch|truncate"
    r"|tee|dd|unlink|shred|rsync|patch|mkdir|sed|perl|ruby|awk|gawk|git|find|xargs|gzip|gunzip"
    r"|bzip2|xz|curl|wget|sort|python[\d.]*|node|bash|sh|zsh|eval)(?![\w-])"
)


def _has_glob(s: str) -> bool:
    return any(ch in GLOB_CHARS for ch in s)


def _split(args: list[str], valued=frozenset()) -> tuple[list[str], list[str]]:
    """(options, positionals); options in ``valued`` consume the next word; ``--`` ends options."""
    opts: list[str] = []
    pos: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1 :])
            break
        if a.startswith("-") and len(a) > 1:
            opts.append(a)
            if a in valued:
                i += 1
        else:
            pos.append(a)
        i += 1
    return opts, pos


def _shorts(opts: list[str]) -> set[str]:
    return {ch for o in opts if not o.startswith("--") for ch in o[1:]}


def _values(args: list[str], flags: tuple[str, ...]) -> list[str]:
    """Values of the given options, in the ``-o X``, ``-oX`` and ``--opt=X`` forms."""
    out: list[str] = []
    for i, a in enumerate(args):
        for f in flags:
            if a == f and i + 1 < len(args):
                out.append(args[i + 1])
            elif f.startswith("--") and a.startswith(f + "="):
                out.append(a[len(f) + 1 :])
            elif not f.startswith("--") and a.startswith(f) and len(a) > len(f) and a[1] != "-":
                out.append(a[len(f) :])
    return out


# --- FROZEN.txt ---------------------------------------------------------------------------------
class Pattern:
    """One FROZEN.txt line. ``dir/*``, ``dir/**`` and ``dir/`` cover everything under ``dir``;
    other patterns with glob characters use fnmatch; a plain path matches exactly (or, if it
    names an existing directory, everything under it)."""

    __slots__ = ("anchor", "kind", "literal", "raw", "stem")

    def __init__(self, raw: str, root: str):
        while raw.startswith("./"):
            raw = raw[2:]
        self.raw = raw
        stem = raw
        for suffix in ("/**", "/*", "/"):
            if raw.endswith(suffix):
                stem = raw[: -len(suffix)]
                break
        if stem != raw and not _has_glob(stem):
            kind = "dir"
        elif _has_glob(raw):
            kind = "glob"
        elif os.path.isdir(os.path.join(root, raw)):
            kind = "dir"
        else:
            kind = "exact"
        self.kind, self.stem = kind, stem
        lit = re.split(r"[*?\[]", raw, maxsplit=1)[0]
        if kind == "glob":
            self.anchor = lit.rsplit("/", 1)[0] if "/" in lit else ""
            self.literal = lit.rstrip("/")
        else:
            self.anchor = self.literal = stem

    def matches(self, rel: str) -> bool:
        if self.kind == "dir":
            return rel == self.stem or rel.startswith(self.stem + "/")
        if self.kind == "exact":
            return rel == self.stem
        return fnmatch.fnmatchcase(rel, self.raw) or (
            self.stem != self.raw and fnmatch.fnmatchcase(rel, self.stem)
        )


class Frozen:
    def __init__(self, root: str, lines: list[str]):
        self.roots: list[str] = []
        for r in (os.path.abspath(root), os.path.realpath(root)):
            if r not in self.roots:
                self.roots.append(r)
        self.patterns = [
            Pattern(s, root) for s in (ln.strip() for ln in lines) if s and not s.startswith("#")
        ]
        alts = []
        for k, p in enumerate(self.patterns):
            if p.literal:
                tail = "" if p.kind == "glob" else r"(?![\w.-])"
                alts.append(f"(?P<p{k}>{re.escape(p.literal)}){tail}")
        self.mention_re = re.compile(r"(?<![\w.-])(?:" + "|".join(alts) + ")") if alts else None

    @classmethod
    def load(cls, root: str) -> Frozen | None:
        try:
            with open(os.path.join(root, "FROZEN.txt"), encoding="utf-8") as fh:
                return cls(root, fh.read().splitlines())
        except FileNotFoundError:
            return None

    def rels(self, path: str) -> list[str]:
        """``path`` relative to the project root, as written and with symlinks resolved."""
        out: list[str] = []
        for p in (path, os.path.realpath(path)):
            for r in self.roots:
                base = r.rstrip(os.sep)
                if p == r:
                    rel = "."
                elif p.startswith(base + os.sep):
                    rel = p[len(base) + 1 :]
                else:
                    continue
                if rel not in out:
                    out.append(rel)
        return out

    def match_rel(self, rel: str, recursive: bool) -> str | None:
        for p in self.patterns:
            if p.matches(rel):
                return rel
        if recursive:  # rm -r / mv / chmod -R on a directory that holds frozen paths
            for p in self.patterns:
                if rel == "." or p.anchor == rel or p.anchor.startswith(rel + "/"):
                    return f"{p.raw} (under {rel})"
        return None

    def match_path(self, path: str, recursive: bool = False) -> str | None:
        for rel in self.rels(path):
            hit = self.match_rel(rel, recursive)
            if hit:
                return hit
        return None

    def match_glob(self, path: str, recursive: bool = False) -> str | None:
        """A target with glob characters: what it expands to now, and what it could match."""
        for p in sorted(glob.glob(path))[:256]:
            hit = self.match_path(p, recursive)
            if hit:
                return hit
        for rel in self.rels(path):
            parts = rel.split("/")
            for p in self.patterns:
                lit = p.anchor if p.kind == "glob" else p.stem
                if fnmatch.fnmatchcase(rel, p.raw) or (
                    p.kind != "glob" and fnmatch.fnmatchcase(lit, rel)
                ):
                    return f"{rel} (matches {p.raw})"
                if p.kind == "dir":  # the glob descends into a frozen directory
                    depth = lit.count("/") + 1
                    if len(parts) > depth and fnmatch.fnmatchcase(lit, "/".join(parts[:depth])):
                        return f"{rel} (matches {p.raw})"
                if recursive and lit:
                    while "/" in lit:
                        lit = lit.rsplit("/", 1)[0]
                        if fnmatch.fnmatchcase(lit, rel):
                            return f"{p.raw} (under {rel})"
        return None

    def mentioned(self, text: str) -> str | None:
        """The first frozen pattern whose literal path appears in ``text``."""
        if self.mention_re is None:
            return None
        m = self.mention_re.search(text)
        return self.patterns[int(m.lastgroup[1:])].raw if m and m.lastgroup else None


# --- Bash ---------------------------------------------------------------------------------------
def _word_start(out: list[str]) -> bool:
    return not out or not out[-1] or out[-1][-1] in " \t\n;&|()<>"


def _walk(cmd: str, i: int, closer: str | None, out, subs, docs) -> int:
    """Quote-aware pass over ``cmd`` from ``i``. Writes the shlex-ready text to ``out`` (comments
    and heredoc bodies removed, quoted/escaped operators swapped for placeholders, substitutions
    lifted into ``subs`` and replaced by markers) and returns the index of ``closer``. ``out``
    None is a dry run that only finds the end of a substitution."""
    n, quote, depth, pending = len(cmd), "", 0, []

    def emit(s: str) -> None:
        if out is not None:
            out.append(s)

    def lift(start: int, end: int) -> None:
        if out is not None:
            subs.append(cmd[start:end])
            emit(f"{MARK}{len(subs) - 1}{MARK_END}")

    while i < n:
        c = cmd[i]
        if quote == "'":
            if c == "'":
                quote = ""
            emit(c if c == "'" else PLACE.get(c, c))
            i += 1
            continue
        if c == "\\":
            nxt = cmd[i + 1 : i + 2]
            if nxt == "\n":  # line continuation
                i += 2
            elif nxt and nxt in PLACE:
                emit(("\\" if quote else "") + PLACE[nxt])
                i += 2
            else:
                emit(cmd[i : i + 2])
                i += 2
            continue
        if cmd.startswith("$(", i) or (not quote and c in "<>" and cmd.startswith("(", i + 1)):
            j = _walk(cmd, i + 2, ")", None, None, None)
            lift(i + 2, j)
            i = j + 1
            continue
        if c == "`":
            if closer == "`":
                return i
            j = _walk(cmd, i + 1, "`", None, None, None)
            lift(i + 1, j)
            i = j + 1
            continue
        if quote == '"':
            if c == '"':
                quote = ""
            emit(c if c == '"' else PLACE.get(c, c))
            i += 1
            continue
        if c in "'\"":
            quote = c
            emit(c)
            i += 1
            continue
        if c == "#" and (_word_start(out) if out is not None else cmd[i - 1 : i] in " \t\n;&|()"):
            j = cmd.find("\n", i)
            i = n if j < 0 else j
            continue
        if closer == ")" and c in "()":
            if c == ")" and depth == 0:
                return i
            depth += 1 if c == "(" else -1
        if cmd.startswith("<<<", i):
            emit("<<<")
            i += 3
            continue
        if cmd.startswith("<<", i):
            m = HEREDOC_RE.match(cmd, i)
            if m:
                delim = next(g for g in m.group(2, 3, 4) if g is not None)
                pending.append((delim, m.group(1) == "-"))
                emit("<< _heredoc_ ")
                i = m.end()
                continue
        if c == "\n" and pending:
            header = "".join(out).rsplit("\n", 1)[-1] if out is not None else ""
            emit("\n")
            i += 1
            for delim, strip_tabs in pending:
                lines = []
                while i < n:
                    j = cmd.find("\n", i)
                    j = n if j < 0 else j
                    line, i = cmd[i:j], j + 1
                    if (line.lstrip("\t") if strip_tabs else line) == delim:
                        break
                    lines.append(line)
                if docs is not None:
                    docs.append((header, "\n".join(lines)))
            pending = []
            continue
        emit(c)
        i += 1
    if closer is not None or quote:
        raise ValueError("unbalanced quote or substitution")
    return n


def _tokens(text: str) -> list[str]:
    lx = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    lx.commenters = ""
    return list(lx)


def _unwrap(name: str, args: list[str]) -> list[str]:
    valued, i = WRAPPERS[name], 0
    while i < len(args) and args[i].startswith("-") and len(args[i]) > 1:
        if args[i] == "--":
            i += 1
            break
        i += 2 if args[i] in valued else 1
    rest = args[i:]
    return rest[1:] if name == "timeout" and rest else rest  # timeout DURATION cmd


def _sed(args: list[str]) -> tuple[bool, list[str]]:
    inplace, pos, i = False, [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1 :])
            break
        if a.startswith("--"):
            inplace |= a == "--in-place" or a.startswith("--in-place=")
            i += 2 if a in ("--expression", "--file", "--line-length") else 1
            continue
        if a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], start=1):
                if ch == "i":
                    inplace = True
                    break
                if ch in "efl":
                    i += 1 if j == len(a) - 1 else 0  # the value is the next word
                    break
            i += 1
            continue
        pos.append(a)
        i += 1
    return inplace, pos


def _perlish(args: list[str]) -> tuple[bool, list[str], list[str]]:
    """perl/ruby switches: (-i given, positional args, -e/-E code)."""
    inplace, pos, codes, i = False, [], [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1 :])
            break
        if a.startswith("-") and len(a) > 1 and not a.startswith("--"):
            j = 1
            while j < len(a):
                ch = a[j]
                if ch == "i":
                    inplace = True
                    break
                if ch in "eE":
                    if j + 1 < len(a):
                        codes.append(a[j + 1 :])
                    elif i + 1 < len(args):
                        i += 1
                        codes.append(args[i])
                    break
                if ch in "0l":  # optional digits follow
                    j += 1
                    while j < len(a) and a[j].isdigit():
                        j += 1
                    continue
                if ch in "MmIxdDCFV":  # the rest of the word is this switch's argument
                    break
                j += 1
            i += 1
            continue
        pos.append(a)
        i += 1
    return inplace, pos, codes


class Scan:
    """Reads one Bash command for the frozen paths it would write. ``hits`` collects them."""

    def __init__(self, frozen: Frozen, text: str, env: dict[str, str]):
        self.frozen, self.text, self.env = frozen, text, env
        self.hits: list[str] = []
        self.subs: list[str] = []
        self.done: set[int] = set()
        self.dirs: list[str] = []

    def hit(self, desc: str | None) -> None:
        if desc and desc not in self.hits:
            self.hits.append(desc)

    def unknown(self) -> None:
        """A write whose target cannot be read off the command: block if it names a frozen path."""
        self.hit(self.frozen.mentioned(self.text))

    def fallback(self, text: str) -> None:
        if WRITE_HINT_RE.search(text):
            self.hit(self.frozen.mentioned(text))

    def code(self, text: str) -> None:
        """Interpreter code: a statement that writes and names a frozen path. Per statement, so a
        script that reads the canon and writes its own output elsewhere is not caught."""
        for statement in re.split(r"[;\n]", text):
            if CODE_WRITE_RE.search(statement):
                self.hit(self.frozen.mentioned(statement))

    # -- structure
    def script(self, text: str, base: str, depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            self.fallback(text)
            return
        start, out, docs = len(self.subs), [], []
        try:
            _walk(text, 0, None, out, self.subs, docs)
            tokens = _tokens("".join(out))
        except ValueError:
            del self.subs[start:]
            self.fallback(text)
            return
        lifted = range(start, len(self.subs))
        self.run(tokens, base, depth)
        for header, doc in docs:  # a heredoc is data unless a shell or interpreter reads it
            words = re.findall(r"[^\s;&|<>()]+", header.translate(UNPLACE))
            names = {os.path.basename(w) for w in words}
            if names & SHELLS:
                self.script(doc, base, depth + 1)
            elif any(INTERP_RE.match(n) for n in names):
                self.code(doc)
        for k in lifted:
            self.sub(k, base, depth)

    def sub(self, k: int, base: str, depth: int) -> None:
        if k not in self.done and k < len(self.subs):
            self.done.add(k)
            self.script(self.subs[k], base, depth + 1)

    def run(self, tokens: list[str], base: str, depth: int) -> None:
        words: list[str] = []
        redirs: list[str] = []
        prev: str | None = None
        pending: str | None = None
        stack: list[str] = []
        for tok in tokens:
            if tok and all(ch in PUNCT for ch in tok):
                for op in OPS_RE.findall(tok):
                    if op in SEPARATORS:
                        pending = None
                        base = self.close(words, redirs, base, prev, op, depth)
                        words, redirs, prev = [], [], op
                        if op == "(":
                            stack.append(base)
                        elif op == ")" and stack:
                            base = stack.pop()
                    else:
                        if words and words[-1].isdigit():  # the fd in 2>file
                            words.pop()
                        pending = op
                continue
            word = tok.translate(UNPLACE)
            if pending is not None:
                if pending in WRITE_REDIRS and not (
                    pending == ">&" and (word.isdigit() or word == "-")
                ):
                    redirs.append(word)
                pending = None
                continue
            words.append(word)
        self.close(words, redirs, base, prev, None, depth)

    def close(self, words, redirs, base, prev, nxt, depth) -> str:
        """Analyse one simple command; return the base directory for the next one."""
        for w in (*words, *redirs):
            for m in MARK_RE.finditer(w):
                self.sub(int(m.group(1)), base, depth)
        for r in redirs:
            self.target(r, base)
        new = self.segment(words, base, depth) if words else None
        if new is not None and prev not in ("|", "|&") and nxt not in ("|", "|&", "&"):
            return new
        return base

    def segment(self, words: list[str], base: str, depth: int, xargs: bool = False) -> str | None:
        words = list(words)
        while words:
            w = words[0]
            if w in KEYWORDS:
                words.pop(0)
            elif ASSIGN_RE.match(w):
                key, value = w.split("=", 1)
                self.assign(key.rstrip("+"), value, base)
                words.pop(0)
            elif os.path.basename(w) in WRAPPERS:
                xargs = xargs or os.path.basename(w) == "xargs"
                words = _unwrap(os.path.basename(w), words[1:])
            else:
                break
        if not words:
            return None
        name, args = os.path.basename(words[0]), words[1:]
        if name in ("cd", "pushd", "popd"):
            return self.chdir(name, args, base)
        if name in ("export", "declare", "typeset", "local", "readonly"):
            for a in args:
                if ASSIGN_RE.match(a):
                    key, value = a.split("=", 1)
                    self.assign(key.rstrip("+"), value, base)
        elif name in SHELLS:
            self.shell(args, base, depth)
        elif name == "eval":
            self.script(" ".join(args), base, depth + 1)
        elif name == "git":
            self.git(args, base)
        elif name == "find":
            self.find(args, base, depth)
        else:
            targets = self.writes(name, args, base)
            if targets is not None:
                if xargs:  # more targets arrive on stdin
                    self.unknown()
                for word, recursive in targets:
                    self.target(word, base, recursive)
        return None

    # -- paths
    def expand(self, word: str, base: str) -> str | None:
        missing = False

        def var(m: re.Match) -> str:
            nonlocal missing
            key = m.group(1) or m.group(2)
            value = base if key == "PWD" else self.env.get(key)
            if value is None:
                missing = True
                return ""
            return value

        out = VAR_RE.sub(var, word) if "$" in word else word
        return None if missing or "$" in out or MARK in out else out

    def assign(self, key: str, value: str, base: str) -> None:
        expanded = self.expand(value, base)
        self.env[key] = value if expanded is None else expanded

    def resolve(self, word: str, base: str) -> tuple[str, bool] | None:
        """(absolute path, has glob characters), or None when it depends on runtime output."""
        w = self.expand(word, base)
        if w is None:
            return None
        if w.startswith("~"):
            w = os.path.expanduser(w)
        is_glob = False
        if BRACE_RE.search(w):
            w, is_glob = BRACE_RE.sub("*", w), True
        is_glob = is_glob or _has_glob(w)
        return os.path.normpath(w if os.path.isabs(w) else os.path.join(base, w)), is_glob

    def target(self, word: str, base: str, recursive: bool = False) -> None:
        if word == "":
            return
        r = self.resolve(word, base)
        if r is None:
            self.unknown()
            return
        path, is_glob = r
        f = self.frozen
        self.hit(f.match_glob(path, recursive) if is_glob else f.match_path(path, recursive))

    def isdir(self, word: str, base: str) -> bool:
        r = self.resolve(word, base)
        return r is not None and not r[1] and os.path.isdir(r[0])

    # -- commands
    def chdir(self, name: str, args: list[str], base: str) -> str | None:
        if name == "popd":
            return self.dirs.pop() if self.dirs else None
        _, pos = _split(args)
        if not pos:
            return os.path.expanduser("~") if name == "cd" else None
        if pos[0] == "-":
            return None
        r = self.resolve(pos[0], base)
        if r is None or r[1]:
            return None  # unknown directory: later relative paths stay on the old base
        if name == "pushd":
            self.dirs.append(base)
        return r[0]

    def shell(self, args: list[str], base: str, depth: int) -> None:
        i, run_c = 0, False
        while i < len(args) and args[i][:1] in ("-", "+") and args[i] not in ("-", "--"):
            a = args[i]
            if a in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
                i += 2
                continue
            run_c |= not a.startswith("--") and "c" in a[1:]
            i += 1
        if run_c and i < len(args):
            self.script(args[i], base, depth + 1)

    def git(self, args: list[str], base: str) -> None:
        i = 0
        while i < len(args) and args[i].startswith("-"):
            a = args[i]
            if a in ("-C", "--work-tree", "--git-dir", "-c", "--namespace") and i + 1 < len(args):
                if a in ("-C", "--work-tree"):
                    r = self.resolve(args[i + 1], base)
                    base = r[0] if r and not r[1] else base
                i += 2
                continue
            if a.startswith("--work-tree="):
                r = self.resolve(a.split("=", 1)[1], base)
                base = r[0] if r and not r[1] else base
            i += 1
        if i >= len(args):
            return
        valued = {
            "checkout": {"-b", "-B", "--orphan"},
            "restore": {"-s", "--source"},
            "rm": set(),
            "mv": set(),
        }.get(args[i])
        if valued is None:
            return
        opts, pos = _split(args[i + 1 :], valued)
        if args[i] == "restore":  # --staged alone resets the index to HEAD and writes no file
            shorts = _shorts(opts)
            staged = "S" in shorts or "--staged" in opts
            worktree = "W" in shorts or "--worktree" in opts
            source = "s" in shorts or any(o.startswith("--source") for o in opts)
            if staged and not worktree and not source:
                return
        for p in pos:  # refs land here too; they never name a frozen path
            if p.startswith(":/"):  # pathspec relative to the top of the work tree
                p = os.path.join(self.frozen.roots[0], p[2:])
            self.target(p, base, recursive=True)

    def find(self, args: list[str], base: str, depth: int) -> None:
        i = 0
        while i < len(args) and (args[i] in ("-H", "-L", "-P") or args[i].startswith("-O")):
            i += 1
        starts = []
        while i < len(args) and not args[i].startswith("-") and args[i] not in ("(", "!", ","):
            starts.append(args[i])
            i += 1
        starts = starts or ["."]
        expr, j = args[i:], 0
        while j < len(expr):
            a = expr[j]
            if a == "-delete":
                for s in starts:
                    self.target(s, base, recursive=True)
            elif a in ("-exec", "-execdir", "-ok", "-okdir"):
                k = j + 1
                while k < len(expr) and expr[k] not in (";", "+"):
                    k += 1
                for s in starts:  # {} is anything under the start path
                    under = s.rstrip("/") + "/*"
                    sub = [w.replace("{}", under) for w in expr[j + 1 : k]]
                    if sub:
                        self.segment(sub, base, depth + 1)
                j = k
            elif a in ("-fprint", "-fprint0", "-fprintf", "-fls") and j + 1 < len(expr):
                self.target(expr[j + 1], base)
                j += 1
            j += 1

    def writes(self, name: str, args: list[str], base: str) -> list[tuple[str, bool]] | None:
        """[(target word, recursive)] for a command that writes files, else None."""
        if name in ("rm", "chmod", "chown", "chgrp"):
            opts, pos = _split(args)
            recursive = bool(_shorts(opts) & set("rR")) or "--recursive" in opts
            return [(p, recursive) for p in pos]
        if name in SIMPLE_WRITERS:
            return [(p, False) for p in _split(args, SIMPLE_WRITERS[name])[1]]
        if name in ("cp", "mv", "install", "ln"):
            return self.copy_like(name, args, base)
        if name == "dd":
            return [(a[3:], False) for a in args if a.startswith("of=")]
        if name in COMPRESSORS:
            opts, pos = _split(args, {"-S", "--suffix"})
            if _shorts(opts) & set("cltT") or {"--stdout", "--to-stdout", "--list", "--test"} & set(
                opts
            ):
                return None
            return [(p, False) for p in pos]
        if name == "rsync":
            opts, pos = _split(args, {"-e", "--rsh"})
            out = [(pos[-1], True)] if len(pos) >= 2 else []
            if "--remove-source-files" in opts:
                out += [(p, True) for p in pos[:-1]]
            return out
        if name == "curl":
            return [(v, False) for v in _values(args, ("-o", "--output"))]
        if name == "wget":
            return [(v, False) for v in _values(args, ("-O", "--output-document"))]
        if name == "sort":
            return [(v, False) for v in _values(args, ("-o", "--output"))] or None
        if name == "patch":
            _, pos = _split(args, {"-p", "-i", "-o", "-d", "-B", "-D", "-F", "-z", "-V", "-r"})
            return [(v, False) for v in pos[:1] + _values(args, ("-o", "--output"))]
        if name == "sed":
            inplace, pos = _sed(args)
            return [(p, False) for p in pos] if inplace else None
        if name in ("awk", "gawk"):
            joined = " ".join(args)
            if not re.search(r"(?:-i\s*|--include[=\s])inplace\b", joined):
                return None
            _, pos = _split(args, {"-v", "-f", "-F", "-i", "--include", "-e", "-E", "-l", "-W"})
            return [(p, False) for p in pos]
        if name in FORMATTERS:  # rewrite every file under their arguments unless only checking
            opts, pos = _split(args, FORMATTER_VALUED)
            if {"--check", "--diff", "--check-only", "-c"} & set(opts):
                return None
            return [(p, True) for p in pos]
        if name == "ruff" and args:
            opts, pos = _split(args[1:], FORMATTER_VALUED)
            fixes = args[0] == "check" and bool({"--fix", "--unsafe-fixes"} & set(opts))
            if (args[0] == "format" or fixes) and not {"--check", "--diff"} & set(opts):
                return [(p, True) for p in pos or ["."]]
            return None
        if INTERP_RE.match(name):
            return self.interpreter(name, args)
        return None

    def copy_like(self, name: str, args: list[str], base: str) -> list[tuple[str, bool]]:
        valued = {"-t", "-S", "--target-directory", "--suffix"}
        if name == "install":
            valued |= {"-m", "-o", "-g", "--mode", "--owner", "--group"}
        tdirs = _values(args, ("-t", "--target-directory"))
        opts, pos = _split(args, valued)
        shorts = _shorts(opts)
        if name == "install" and ("d" in shorts or "--directory" in opts):
            return [(p, False) for p in pos]
        tree = name == "mv" or (
            name == "cp"
            and (bool(shorts & set("rRa")) or bool({"--recursive", "--archive"} & set(opts)))
        )
        no_dir = "T" in shorts or "--no-target-directory" in opts
        if tdirs:
            dest, srcs, into = tdirs[-1], pos, True
        elif len(pos) >= 2:
            dest, srcs = pos[-1], pos[:-1]
            into = not no_dir and (len(srcs) > 1 or dest.endswith("/") or self.isdir(dest, base))
        elif len(pos) == 1 and name == "ln":
            dest, srcs, into = ".", pos, True
        else:
            return []
        out = [(s, True) for s in srcs] if name == "mv" else []
        out.append((dest, False))
        if into:
            out += [(dest.rstrip("/") + "/" + os.path.basename(s.rstrip("/")), tree) for s in srcs]
        return out

    def interpreter(self, name: str, args: list[str]) -> list[tuple[str, bool]] | None:
        if name.startswith("python"):
            for k, a in enumerate(args):
                if a == "-c" and k + 1 < len(args):
                    self.code(args[k + 1])
                    break
                if a.startswith("-c"):
                    self.code(a[2:])
                    break
                if a == "-m" or not a.startswith("-"):
                    break
            return None
        if name == "node":
            for k, a in enumerate(args):
                if a in ("-e", "--eval", "-p", "--print") and k + 1 < len(args):
                    self.code(args[k + 1])
                elif a.startswith(("--eval=", "--print=")):
                    self.code(a.split("=", 1)[1])
            return None
        inplace, pos, codes = _perlish(args)  # perl, ruby
        for c in codes:
            self.code(c)
        return [(p, False) for p in pos] if inplace else None


def scan_bash(frozen: Frozen, command: str, cwd: str, root: str) -> list[str]:
    env = dict(os.environ)
    env.setdefault("CLAUDE_PROJECT_DIR", root)
    scan = Scan(frozen, command, env)
    try:
        scan.script(command, cwd)
    except Exception as exc:  # a bug in the guard must not wedge the session
        print(
            f"deny_frozen: warning: internal error ({exc!r}); conservative check", file=sys.stderr
        )
        scan.fallback(command)
    return scan.hits


def check(payload: dict, root: str) -> list[str]:
    """The frozen paths this tool call would write (empty: allow)."""
    root = os.path.abspath(root)
    frozen = Frozen.load(root)
    if frozen is None or not frozen.patterns:
        return []
    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    if not isinstance(tool, str) or not isinstance(ti, dict):
        return []
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) and os.path.isabs(cwd) else root
    if tool == "Bash":
        command = ti.get("command")
        return scan_bash(frozen, command, cwd, root) if isinstance(command, str) else []
    if tool in FILE_TOOLS or WRITEISH_TOOL.search(tool):
        hits = []
        for key in ("file_path", "notebook_path"):
            path = ti.get(key)
            if isinstance(path, str) and path:
                path = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
                hit = frozen.match_path(path)
                if hit:
                    hits.append(hit)
        return hits
    return []


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            raise ValueError("not a JSON object")
    except ValueError as exc:
        print(f"deny_frozen: warning: unreadable hook payload ({exc}); allowed", file=sys.stderr)
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or SCRIPT_ROOT
    try:
        hits = check(payload, root)
    except Exception as exc:  # never wedge the session
        print(f"deny_frozen: warning: internal error ({exc!r}); allowed", file=sys.stderr)
        return 0
    for h in hits[:5]:
        print(REASON.format(h), file=sys.stderr)
    return 2 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
