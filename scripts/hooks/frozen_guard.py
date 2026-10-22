#!/usr/bin/env python3
"""PreToolUse guard for the frozen toolbox (CLAUDE.md, Frozen toolbox; FROZEN.txt).

Advisory text does not stop an unattended session from "just fixing" the oracle or a test, so
OVERNIGHT_LOOP.md Part 1 §6 makes the freeze a hook: deterministic, and it fires in every
permission mode. ``deny_frozen.sh`` runs this file with ``python3 -I`` before every tool call. It
reads the hook payload on stdin and exits 2 (stderr is shown to Claude) when the call would WRITE
a path listed in FROZEN.txt. Reading a frozen file is always fine.

- FROZEN.txt: one path or glob per line; ``#`` starts a comment (whole line or after whitespace);
  read as UTF-8 with or without a BOM. A FROZEN.txt that exists but cannot be read or decoded
  (UTF-16, NUL bytes, permissions) blocks every write-capable tool call until it is fixed.
- Edit / Write / MultiEdit / NotebookEdit: the file path, resolved against the payload ``cwd``
  and checked both as written and with symlinks resolved. Paths outside the project are allowed.
- Bash: the command is tokenised with ``shlex`` after a quote-aware pass that removes comments
  and heredoc bodies (not ``<<`` inside ``(( ))``) and lifts out ``$(...)``, backtick and
  ``<(...)`` substitutions. Then each simple command is read for what it writes: redirections,
  tee, sed/perl/ruby/awk in-place, mv/cp/install/ln (``-t DIR`` also inside an option cluster),
  rm/rmdir, chmod/chown, touch/truncate/mkdir, dd of=, tar -x/unzip, formatters (black, isort,
  ruff format/--fix, also as ``python -m``), git checkout/restore/rm/mv/clean/submodule deinit,
  find -delete/-exec, xargs, ``bash -c``/eval/trap/function bodies, ``env -C``, and any
  statement of ``-c``/``-e``/heredoc interpreter code that names a frozen path and writes.
  ``cd``/``pushd`` change the base for later relative paths in a chain (not across a pipe or out
  of a subshell); ``$VAR`` is expanded from the environment and earlier assignments.
- A write target that cannot be read off the command (``rm "$f"``, ``sed -i ... $(grep ...)``,
  ``... | xargs sed -i``, a ``for``/``read`` loop variable) is traced to what produces it: the
  substitution, the commands piped into xargs or read, the loop list. It is blocked when that
  producer names a frozen path or a directory holding one (``.`` included), or is a path-less
  lister (git ls-files/grep/diff/status, grep -r, rg, find, ls) run from such a directory. A
  target with a literal directory in front (``runs/$f``) is judged by that directory alone. A
  variable with no producer in the command (``rm -rf "$TMP_DIR"``) is allowed unless the literal
  path after it names a frozen path (``"$ROOT/FROZEN.txt"``). A frozen literal that is only read
  elsewhere in the chain, or that sits inside another relative path (``runs/tests``), is no
  write to it. A command shlex cannot tokenise is blocked when it names a frozen path next to
  any write operator or command word. Blocks from these heuristics say why.

It is a guard against accidents and casual workarounds, not a sandbox. Not covered: a script or
program that writes a frozen file from its own code (``python scripts/calibrate.py``, ``bash
x.sh``, ``make``, ``source``), patches applied from a diff (``patch < x.diff``, ``git apply``),
tree-wide git moves (branch switches, ``git reset --hard``, ``git stash``, ``git pull``, ``git
submodule update``), the lines of a list file or heredoc that feeds xargs or read (``xargs -a
list`` and ``xargs rm < list`` are judged by the list's name), shell function arguments and
``sh -c '...' _ args`` positional parameters (``$1``, ``$@``) unless xargs or ``find -exec``
feeds them, GNU parallel, aliases, and archive tools other than tar/unzip; git history and CI
are the backstop there. It must be fast and must never wedge a session, so it uses the standard
library only, starts no subprocess, and allows the call with a warning on an unreadable payload,
a missing FROZEN.txt or an internal error (a Bash command then gets the conservative check).
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
UNREADABLE = (
    "frozen: FROZEN.txt unreadable: {}; every write is blocked until it is UTF-8 text again "
    "(only Hunter edits FROZEN.txt; CLAUDE.md, Frozen toolbox)"
)
UNRESOLVED = (
    "unresolved write target {} {}: the path cannot be read off the command; "
    "name the path literally or split the command"
)
SCRIPT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
WRITEISH_TOOL = re.compile(r"write|edit", re.I)  # e.g. an MCP write_file tool with a file_path
MAX_DEPTH = 6  # nesting of bash -c / eval / $(...) before falling back to the literal check
PROBE_BUDGET = 400  # provenance steps per unresolved target

# --- shell lexing -------------------------------------------------------------------------------
PUNCT = "();<>|&\n"  # shlex punctuation; quoted or escaped copies are swapped for private-use chars
PLACE = {ch: chr(0xE000 + k) for k, ch in enumerate(PUNCT)}
UNPLACE = {ord(v): k for k, v in PLACE.items()}
# a lifted $(...) / `...` / <(...) substitution is written MARK<n>MARK_END
MARK, MARK_END = "\ue100", "\ue101"
MARK_RE = re.compile(MARK + r"(\d+)" + MARK_END)
OPS_RE = re.compile(r"&>>|&>|>>|>\||>&|<>|<<<|<<|<&|&&|\|\||\|&|;;|[;&|()\n<>]")
SEPARATORS = frozenset({";", "&&", "||", "|", "|&", "&", ";;", "\n", "(", ")"})
PIPES = frozenset({"|", "|&"})
WRITE_REDIRS = frozenset({">", ">>", ">|", "&>", "&>>", "<>", ">&"})
READ_REDIRS = frozenset({"<", "<<<"})
HEREDOC_RE = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([^\s;&|<>()'\"`]+))")
ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*\+?=")
VAR_RE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
PIECE_RE = re.compile(  # what can leave a word unresolved: a substitution or a parameter
    MARK + r"(\d+)" + MARK_END + r"|\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)"
    r"|\$\{[#!]?([A-Za-z_]\w*)[^}]*\}|\$\{[^}]*\}|\$[@*#?$!\d-]"
)
BRACE_RE = re.compile(r"\{[^{}]*(?:,|\.\.)[^{}]*\}")
GLOB_CHARS = frozenset("*?[")
PREFIX_RE = re.compile(r"[^\s'\"`=(),;:<>|&\[\]]*\Z")  # the path characters before a mention

# --- what writes --------------------------------------------------------------------------------
KEYWORDS = frozenset({"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!"})
KEYWORDS |= {"{", "}"}
OPENERS = frozenset({"while", "until", "for", "select", "if", "case", "{"})
CLOSERS = frozenset({"done", "fi", "esac", "}"})
WRAPPERS = {  # command prefixes -> their options that take a separate value
    "sudo": {"-u", "-g", "-C", "-D", "-p", "-r", "-t", "-U", "-h", "--chdir"},
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
CHDIR_OPTS = {"env": ("-C", "--chdir"), "sudo": ("-D", "--chdir")}
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
TAR_LONG_VALUED = frozenset(
    {"--file", "--directory", "--files-from", "--exclude-from", "--exclude", "--format"}
    | {"--blocking-factor", "--use-compress-program", "--transform", "--xform", "--owner"}
    | {"--group", "--mode", "--newer", "--listed-incremental", "--label", "--starting-file"}
)
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
    r"|bzip2|xz|curl|wget|sort|python[\d.]*|node|bash|sh|zsh|eval|tar|unzip|trap)(?![\w-])"
)

# --- what lists paths (the producers an unresolved write target is traced to) -------------------
GREPS = frozenset({"grep", "egrep", "fgrep", "zgrep"})
GREP_VALUED = {"-e", "-f", "-m", "-A", "-B", "-C", "-d", "-D", "--regexp", "--file"}
GREP_VALUED |= {"--max-count", "--after-context", "--before-context", "--context", "--label"}
RGS = frozenset({"rg", "ag", "ack", "ack-grep"})
RG_VALUED = {"-e", "-f", "-g", "-t", "-T", "-m", "-A", "-B", "-C", "-j", "-M", "-E", "--glob"}
RG_VALUED |= {"--iglob", "--type", "--type-not", "--regexp", "--file", "--max-count"}
FDS = frozenset({"fd", "fdfind"})
FD_VALUED = {"-e", "-t", "-E", "-d", "-x", "-X", "-j", "--extension", "--type", "--exclude"}
GIT_LISTERS = frozenset(
    {"ls-files", "grep", "diff", "status", "ls-tree", "show", "log", "whatchanged"}
    | {"diff-tree", "diff-index", "diff-files", "ls-others"}
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


def _gnu(args: list[str], short_valued: str = "", long_valued=frozenset()):
    """GNU-style options: (flags, values, positionals). Short clusters are walked letter by
    letter, so ``-vt DIR`` and ``-vtDIR`` both give ``t`` the value ``DIR``. ``flags`` holds each
    short letter and each long option name; ``values`` maps an option to its values in order."""
    flags: set[str] = set()
    values: dict[str, list[str]] = {}
    pos: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1 :])
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            flags.add(name)
            if eq:
                values.setdefault(name, []).append(val)
            elif name in long_valued and i + 1 < len(args):
                i += 1
                values.setdefault(name, []).append(args[i])
        elif a.startswith("-") and len(a) > 1:
            for j in range(1, len(a)):
                ch = a[j]
                flags.add(ch)
                if ch in short_valued:
                    if j + 1 < len(a):
                        values.setdefault(ch, []).append(a[j + 1 :])
                    elif i + 1 < len(args):
                        i += 1
                        values.setdefault(ch, []).append(args[i])
                    break
        else:
            pos.append(a)
        i += 1
    return flags, values, pos


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


def _parts_match(name: list[str], pat: list[str]) -> bool:
    if not pat:
        return not name
    if pat[0] == "**":
        return any(_parts_match(name[k:], pat[1:]) for k in range(len(name) + 1))
    return bool(name) and fnmatch.fnmatchcase(name[0], pat[0]) and _parts_match(name[1:], pat[1:])


def _gmatch(name: str, pat: str, cross: bool = False) -> bool:
    """Shell-glob match: ``*`` stops at ``/`` and ``**`` spans directories. ``cross`` is git
    pathspec matching, where ``*`` crosses ``/`` (``'*.py'`` names every Python file)."""
    if cross:
        return fnmatch.fnmatchcase(name, pat)
    return _parts_match(name.split("/"), pat.split("/"))


# --- FROZEN.txt ---------------------------------------------------------------------------------
class Unreadable(Exception):
    """FROZEN.txt exists but cannot be read as text: fail closed for writes."""


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


def _entries(lines: list[str]) -> list[str]:
    """FROZEN.txt lines without comments: ``#`` at the start or after whitespace."""
    out = []
    for ln in lines:
        s = re.sub(r"(?:^|\s)#.*", "", ln).strip()
        if s:
            out.append(s)
    return out


class Frozen:
    def __init__(self, root: str, lines: list[str]):
        self.roots: list[str] = []
        for r in (os.path.abspath(root), os.path.realpath(root)):
            if r not in self.roots:
                self.roots.append(r)
        self.patterns = [Pattern(s, root) for s in _entries(lines)]
        alts = []
        for k, p in enumerate(self.patterns):
            if p.literal:
                tail = "" if p.kind == "glob" else r"(?![\w.-])"
                alts.append(f"(?P<p{k}>{re.escape(p.literal)}){tail}")
        self.mention_re = re.compile(r"(?<![\w.-])(?:" + "|".join(alts) + ")") if alts else None

    @classmethod
    def load(cls, root: str) -> Frozen | None:
        path = os.path.join(root, "FROZEN.txt")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise Unreadable(f"{exc.strerror or exc}") from exc
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise Unreadable(f"not UTF-8 ({exc.reason} at byte {exc.start})") from exc
        if "\x00" in text:
            raise Unreadable("NUL bytes (saved as UTF-16?)")
        return cls(root, text.splitlines())

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

    def match_glob(self, path: str, recursive: bool = False, cross: bool = False) -> str | None:
        """A target with glob characters: what it expands to now, and what it could match.
        ``cross``: a git pathspec, whose ``*`` also matches ``/``."""
        for p in sorted(glob.glob(path))[:256]:
            hit = self.match_path(p, recursive)
            if hit:
                return hit
        for rel in self.rels(path):
            parts = rel.split("/")
            for p in self.patterns:
                lit = p.anchor if p.kind == "glob" else p.stem
                if fnmatch.fnmatchcase(rel, p.raw) or (
                    p.kind != "glob" and _gmatch(lit, rel, cross)
                ):
                    return f"{rel} (matches {p.raw})"
                if p.kind == "dir":  # the glob descends into a frozen directory
                    depth = lit.count("/") + 1
                    if len(parts) > depth and _gmatch(lit, "/".join(parts[:depth]), cross):
                        return f"{rel} (matches {p.raw})"
                if recursive and lit:
                    while "/" in lit:
                        lit = lit.rsplit("/", 1)[0]
                        if _gmatch(lit, rel, cross):
                            return f"{p.raw} (under {rel})"
        return None

    def rooted(self, prefix: str) -> bool:
        """Could ``prefix`` followed by a frozen literal still name the project's path? It
        cannot when the prefix is another relative directory (``runs/tests``) or an absolute
        directory other than the root; a variable, ``~``, ``..`` or a lone ``/`` might."""
        if not prefix or prefix == "/" or ".." in prefix:
            return True
        if re.search("[$~`{}" + MARK + "]", prefix):
            return True
        if prefix.startswith("/"):
            return os.path.normpath(prefix) in self.roots
        return prefix.replace("./", "") == ""

    def mentioned(self, text: str) -> str | None:
        """The first frozen pattern whose literal path appears in ``text`` as a path of its own
        (not as the tail of another relative path such as ``runs/tests``)."""
        if self.mention_re is None:
            return None
        for m in self.mention_re.finditer(text):
            start = m.start()
            if start and text[start - 1] == "/":
                found = PREFIX_RE.search(text, max(0, start - 256), start)
                if not self.rooted(found.group(0) if found else "/"):
                    continue
            if m.lastgroup:
                return self.patterns[int(m.lastgroup[1:])].raw
        return None


# --- Bash ---------------------------------------------------------------------------------------
def _word_start(out: list[str]) -> bool:
    return not out or not out[-1] or out[-1][-1] in " \t\n;&|()<>"


def _walk(cmd: str, i: int, closer: str | None, out, subs, docs) -> int:
    """Quote-aware pass over ``cmd`` from ``i``. Writes the shlex-ready text to ``out`` (comments
    and heredoc bodies removed, quoted/escaped operators swapped for placeholders, substitutions
    lifted into ``subs`` and replaced by markers) and returns the index of ``closer``. ``out``
    None is a dry run that only finds the end of a substitution."""
    n, quote, depth, pending, arith = len(cmd), "", 0, [], 0

    def emit(s: str) -> None:
        if out is not None:
            out.append(s)

    def lift(start: int, end: int) -> None:
        if out is not None:
            subs.append(cmd[start:end])
            emit(f"{MARK}{len(subs) - 1}{MARK_END}")

    def at_word_start() -> bool:
        return _word_start(out) if out is not None else cmd[i - 1 : i] in ("", " ", "\t", "\n")

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
        if arith:  # inside (( ... )): `<<` is a shift, not a heredoc
            arith += 1 if c == "(" else -1 if c == ")" else 0
        elif c == "(" and cmd.startswith("((", i) and at_word_start():
            arith = 1
        if closer == ")" and c in "()":
            if c == ")" and depth == 0:
                return i
            depth += 1 if c == "(" else -1
        if not arith and cmd.startswith("<<<", i):
            emit("<<<")
            i += 3
            continue
        if not arith and cmd.startswith("<<", i):
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


def _nest(words: list[str]) -> int:
    """How many compound commands this simple command's leading keywords open (+) or close (-)."""
    d, i = 0, 0
    while i < len(words):
        w = words[i]
        if w == "function":
            i += 2
            continue
        if w in OPENERS:
            d += 1
        elif w in CLOSERS:
            d -= 1
        elif w not in KEYWORDS:
            break
        i += 1
    return d


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
    """Reads one Bash command for the frozen paths it would write. ``hits`` collects them as
    (what, why); ``why`` is set when a heuristic, not a literal target, made the call."""

    def __init__(self, frozen: Frozen, text: str, env: dict[str, str]):
        self.frozen, self.text, self.env = frozen, text, env
        self.hits: list[tuple[str, str | None]] = []
        self.subs: list[str] = []
        self.done: set[int] = set()
        self.dirs: list[str] = []
        # provenance of write targets that cannot be read off the command
        self.unknowns: list[tuple[str, str, bool]] = []  # (word, base, recursive), settled last
        self.prov: dict[str, list[tuple]] = {}  # variable -> ("value", word, base) | ("seg", seg)
        self.sub_segs: dict[int, list[tuple]] = {}  # substitution -> its simple commands
        self.read_vars: set[str] = set()
        self.loop_inputs: list[tuple] = []  # `done < <(...)`: input of a while-read loop
        self.feed: list[tuple] = []  # what is piped or redirected into the current command
        self.serial = 0
        self.budget = 0

    def hit(self, desc: str | None, why: str | None = None) -> None:
        if desc and all(desc != h for h, _ in self.hits):
            self.hits.append((desc, why))

    def unknown(self, word: str, base: str, recursive: bool = False) -> None:
        """A write target that cannot be read off the command; judged by settle()."""
        self.unknowns.append((word, base, recursive))

    def fallback(self, text: str) -> None:
        if WRITE_HINT_RE.search(text):
            self.hit(
                self.frozen.mentioned(text),
                "the command could not be parsed and names this frozen path next to a write "
                "operator or command word; simplify or split the command",
            )

    def code(self, text: str) -> None:
        """Interpreter code: a statement that writes and names a frozen path. Per statement, so a
        script that reads the canon and writes its own output elsewhere is not caught."""
        for statement in re.split(r"[;\n]", text):
            if CODE_WRITE_RE.search(statement):
                s = " ".join(statement.split())
                self.hit(
                    self.frozen.mentioned(statement),
                    f"interpreter code `{s[:100]}` writes and names this frozen path; "
                    "read the frozen file in a separate statement or step",
                )

    # -- structure
    def script(self, text: str, base: str, depth: int = 0, sub: int | None = None) -> None:
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
        log = self.sub_segs.setdefault(sub, []) if sub is not None else None
        self.run(tokens, base, depth, log)
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
            self.script(self.subs[k], base, depth + 1, sub=k)

    def run(self, tokens: list[str], base: str, depth: int, log: list | None = None) -> None:
        words: list[str] = []
        redirs: list[str] = []
        inputs: list[str] = []
        prev: str | None = None
        pending: str | None = None
        stack: list[str] = []
        nest = 0  # open compound commands: loops, if, { }, ( )
        elem: list[tuple] = []  # simple commands of the current pipeline element
        upstream: list[tuple] = []  # simple commands piped into the current one
        for tok in tokens:
            if tok and all(ch in PUNCT for ch in tok):
                for op in OPS_RE.findall(tok):
                    if op not in SEPARATORS:
                        if words and words[-1].isdigit():  # the fd in 2>file
                            words.pop()
                        pending = op
                        continue
                    pending = None
                    seg = (words, inputs, base)
                    base, nest = self.close(seg, redirs, prev, op, depth, upstream, nest)
                    if words or inputs:
                        elem.append(seg)
                        if log is not None:
                            log.append(seg)
                    if op in PIPES:
                        upstream, elem = upstream + elem, []
                    elif nest == 0 and op not in ("(", ")"):
                        upstream, elem = [], []
                    words, redirs, inputs, prev = [], [], [], op
                    if op == "(":
                        stack.append(base)
                        nest += 1
                    elif op == ")":
                        base = stack.pop() if stack else base
                        nest = max(0, nest - 1)
                continue
            word = tok.translate(UNPLACE)
            if pending is not None:
                if pending in WRITE_REDIRS and not (
                    pending == ">&" and (word.isdigit() or word == "-")
                ):
                    redirs.append(word)
                elif pending in READ_REDIRS:
                    inputs.append(word)
                pending = None
                continue
            words.append(word)
        seg = (words, inputs, base)
        self.close(seg, redirs, prev, None, depth, upstream, nest)
        if log is not None and (words or inputs):
            log.append(seg)

    def close(self, seg, redirs, prev, nxt, depth, upstream, nest) -> tuple[str, int]:
        """Analyse one simple command; return the base directory for the next one and the
        compound-command depth after it."""
        words, inputs, base = seg
        for w in (*words, *redirs, *inputs):
            for m in MARK_RE.finditer(w):
                self.sub(int(m.group(1)), base, depth)
        for r in redirs:
            self.target(r, base)
        nest = max(0, nest + _nest(words))
        if inputs and all(w in KEYWORDS for w in words):  # `done < <(...)`, `} < file`
            self.loop_inputs.append(([], list(inputs), base))
        self.feed = list(upstream) + ([([], list(inputs), base)] if inputs else [])
        new = self.segment(words, base, depth) if words else None
        if new is not None and prev not in PIPES and nxt not in ("|", "|&", "&"):
            return new, nest
        return base, nest

    def segment(self, words: list[str], base: str, depth: int) -> str | None:
        words = list(words)
        ph = None  # placeholder for the paths xargs reads from stdin
        while words:
            w = words[0]
            name = os.path.basename(w)
            if w in KEYWORDS:
                words.pop(0)
            elif w == "function":  # function NAME { body; }
                words = words[2:]
            elif ASSIGN_RE.match(w):
                key, value = w.split("=", 1)
                self.assign(key.rstrip("+"), value, base)
                words.pop(0)
            elif name == "xargs":
                ph, words = self.xargs(words[1:], base)
            elif name in WRAPPERS:
                base, words = self.wrapper(name, words[1:], base)
            else:
                break
        if not words:
            return None
        name, args = os.path.basename(words[0]), words[1:]
        if ph and (name in SHELLS or name == "eval"):  # sh -c '... "$@"' _ <stdin paths>
            self.unknown(ph, base, True)
        if name in ("cd", "pushd", "popd"):
            return self.chdir(name, args, base)
        if name in ("export", "declare", "typeset", "local", "readonly"):
            for a in args:
                if ASSIGN_RE.match(a):
                    key, value = a.split("=", 1)
                    self.assign(key.rstrip("+"), value, base)
        elif name in ("for", "select"):
            self.loop(args, base)
        elif name in ("read", "mapfile", "readarray"):
            self.read(name, args)
        elif name == "trap":
            _, pos = _split(args)
            if len(pos) >= 2:
                self.script(pos[0], base, depth + 1)
        elif name in SHELLS:
            self.shell(args, base, depth)
        elif name == "eval":
            self.script(" ".join(args), base, depth + 1)
        elif name == "git":
            self.git(args, base)
        elif name == "find":
            self.find(args, base, depth)
        else:
            for word, recursive in self.writes(name, args, base) or ():
                self.target(word, base, recursive)
        return None

    def placeholder(self, kind: str, sources: list[tuple]) -> str:
        """A variable that stands for paths produced elsewhere (xargs stdin, find's {})."""
        self.serial += 1
        key = f"_{kind}_{self.serial}"
        self.prov[key] = sources
        return "${" + key + "}"

    def xargs(self, args: list[str], base: str) -> tuple[str, list[str]]:
        valued, repl, i = WRAPPERS["xargs"], None, 0
        while i < len(args) and args[i].startswith("-") and len(args[i]) > 1:
            a = args[i]
            if a == "--":
                i += 1
                break
            if a == "-I" and i + 1 < len(args):
                repl = args[i + 1]
            elif a.startswith("-I"):
                repl = a[2:]
            elif a == "-i" or a.startswith("--replace"):  # deprecated spellings of -I {}
                repl = a.split("=", 1)[1] if "=" in a else "{}"
            elif a.startswith("-i"):
                repl = a[2:]
            i += 2 if a in valued else 1
        lists = _values(args[:i], ("-a", "--arg-file"))  # judged by name, like `< FILE`
        feed = self.feed + ([([], lists, base)] if lists else [])
        ph = self.placeholder("xargs_stdin", [("seg", s) for s in feed])
        rest = args[i:]
        if not rest:
            return ph, []
        if repl:
            return ph, [rest[0]] + [w.replace(repl, ph) for w in rest[1:]]
        return ph, [*rest, ph]

    def wrapper(self, name: str, args: list[str], base: str) -> tuple[str, list[str]]:
        """Strip a command prefix; ``env -C DIR`` / ``sudo -D DIR`` move the base and
        ``env -S 'cmd args'`` splits its string into words."""
        chdir = CHDIR_OPTS.get(name, ())
        if chdir:
            for d in _values(args[: self._optend(name, args)], chdir):
                base = self._dir(d, base)
        if name == "env":
            split = _values(args[: self._optend(name, args)], ("-S", "--split-string"))
            if split:
                try:
                    return base, shlex.split(split[-1]) + _unwrap(name, args)
                except ValueError:
                    pass
        return base, _unwrap(name, args)

    @staticmethod
    def _optend(name: str, args: list[str]) -> int:
        valued, i = WRAPPERS[name], 0
        while i < len(args) and args[i].startswith("-") and len(args[i]) > 1 and args[i] != "--":
            i += 2 if args[i] in valued else 1
        return min(i, len(args))

    def _dir(self, word: str, base: str) -> str:
        r = self.resolve(word, base)
        return r[0] if r and not r[1] else base

    def loop(self, args: list[str], base: str) -> None:
        """``for VAR in WORDS``: VAR is any of WORDS."""
        if len(args) >= 2 and args[1] == "in" and re.fullmatch(r"[A-Za-z_]\w*", args[0]):
            self.env.pop(args[0], None)
            self.prov.setdefault(args[0], []).extend(("value", w, base) for w in args[2:])

    def read(self, name: str, args: list[str]) -> None:
        """``read VAR`` / ``mapfile ARR``: the variables hold what is piped or redirected in."""
        if name == "read":
            _, pos = _split(args, {"-a", "-d", "-i", "-n", "-N", "-p", "-t", "-u"})
            names = pos + _values(args, ("-a",)) or ["REPLY"]
        else:
            _, pos = _split(args, {"-d", "-n", "-O", "-s", "-u", "-C", "-c"})
            names = pos[-1:] or ["MAPFILE"]
        for v in names:
            self.env.pop(v, None)
            self.read_vars.add(v)
            self.prov.setdefault(v, []).extend(("seg", s) for s in self.feed)

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
            self.unknown(word, base, recursive)
            return
        path, is_glob = r
        f = self.frozen
        self.hit(f.match_glob(path, recursive) if is_glob else f.match_path(path, recursive))

    def isdir(self, word: str, base: str) -> bool:
        r = self.resolve(word, base)
        return r is not None and not r[1] and os.path.isdir(r[0])

    # -- unresolved targets: trace them to what produces them
    def settle(self) -> None:
        for word, base, recursive in self.unknowns:
            self.budget = PROBE_BUDGET
            found = self.probe(word, base, recursive, 0, set())
            if found:
                self.hit(found[0], UNRESOLVED.format(self.show(word), found[1]))

    def show(self, word: str) -> str:
        """A word as Claude wrote it: substitutions put back, placeholders named."""
        word = re.sub(r"\$\{_xargs_stdin_\d+\}", "<xargs input>", word)
        word = re.sub(r"\$\{_find_path_\d+\}", "<find path>", word)
        word = MARK_RE.sub(lambda m: "$(" + self.subs[int(m.group(1))] + ")", word)
        word = " ".join(word.split())
        return "`" + (word if len(word) <= 80 else word[:77] + "...") + "`"

    def partial(self, word: str, base: str) -> tuple[str, list[tuple[int, int, str, object]]]:
        """``word`` with each resolvable ``$VAR`` expanded, and the spans that stay unresolved:
        (start, end, kind, key), kind ``sub`` (key: substitution index), ``var`` (key: name) or
        ``special`` (``$1``, ``$@``, ...)."""
        parts: list[str] = []
        pieces: list[tuple[int, int, str, object]] = []
        size = pos = 0
        for m in PIECE_RE.finditer(word):
            lit = word[pos : m.start()]
            parts.append(lit)
            size += len(lit)
            pos = m.end()
            tok = m.group(0)
            if m.group(1) is not None:
                kind, key = "sub", int(m.group(1))
            elif m.group(2) or m.group(3):
                key = m.group(2) or m.group(3)
                value = base if key == "PWD" else self.env.get(key)
                if value is not None and "$" not in value and MARK not in value:
                    parts.append(value)
                    size += len(value)
                    continue
                kind = "var"
            elif m.group(4):
                kind, key = "var", m.group(4)
            else:
                kind, key = "special", tok
            parts.append(tok)
            pieces.append((size, size + len(tok), kind, key))
            size += len(tok)
        parts.append(word[pos:])
        return "".join(parts), pieces

    def probe(self, word: str, base: str, recursive: bool, depth: int, seen: set):
        """Could the write target ``word`` be a frozen path? (frozen match, where: a phrase that
        says why) or None."""
        self.budget -= 1
        if self.budget < 0 or depth > MAX_DEPTH:
            return None
        f = self.frozen
        r = self.resolve(word, base)
        if r is not None:
            path, is_glob = r
            isdir = not is_glob and os.path.isdir(path)
            hit = f.match_glob(path, True) if is_glob else f.match_path(path, recursive or isdir)
            return (hit, self.where(word, is_glob, isdir)) if hit else None
        text, pieces = self.partial(word, base)
        if not pieces:
            return None
        head, tail = text[: pieces[0][0]], text[pieces[-1][1] :]
        if "/" in head and head.rsplit("/", 1)[0] not in ("", "."):
            return self.probe(head.rsplit("/", 1)[0], base, True, depth + 1, seen)  # runs/$f
        start, end, kind, key = pieces[0]
        traced = False
        for src in self.sources(kind, key, seen):
            traced = True
            if src[0] == "value":  # substitute a value the variable can hold, then look again
                value = text[:start] + src[1] + text[end:]
                found = self.probe(value, src[2] or base, recursive, depth + 1, seen)
            else:
                found = self.probe_seg(src[1], depth + 1, seen)
            if found:
                return found
        if kind == "sub" or not traced:  # "$ROOT/FROZEN.txt", "$(git rev-parse ...)/data"
            rest = tail.lstrip("/")
            if tail.startswith("/") and rest:
                path = os.path.join(f.roots[0], rest)
                found = self.probe(path, base, recursive, depth + 1, seen)
                if found:
                    lead = self.show(text[:end])
                    return (
                        found[0],
                        f"ends in `{tail}`, a frozen path if {lead} is the project root",
                    )
        return None

    def where(self, word: str, is_glob: bool, isdir: bool) -> str:
        if is_glob:
            return f"could match {self.show(word)}"
        if isdir:
            return f"could be anything under {self.show(word)}"
        return f"could be {self.show(word)}"

    def sources(self, kind: str, key, seen: set) -> list[tuple]:
        """What produces an unresolved piece: ("value", word, base) or ("seg", seg)."""
        if (kind, key) in seen:
            return []
        seen.add((kind, key))
        if kind == "sub":
            return [("seg", s) for s in self.sub_segs.get(key, [])]
        if kind != "var":
            return []
        out: list[tuple] = []
        value = self.env.get(key)
        if value is not None and ("$" in value or MARK in value):
            out.append(("value", value, None))
        out += self.prov.get(key, [])
        if key in self.read_vars:
            out += [("seg", s) for s in self.loop_inputs]
        return out

    def probe_seg(self, seg: tuple, depth: int, seen: set):
        """Could a command that produces paths (for xargs, a substitution, a read loop) list a
        frozen path? It can if it names one, or a directory holding one, or lists ``.`` by
        default (git ls-files, grep -r, find, ls) from such a directory."""
        words, inputs, base = seg
        for w in inputs:
            found = self.probe(w, base, False, depth, seen)
            if found:
                return found
        found = self._probe_words(list(words), base, depth, seen)
        if found and "(listed by" not in found[1]:
            return found[0], f"{found[1]} (listed by {self.show(' '.join(words))})"
        return found

    def _probe_words(self, words: list[str], base: str, depth: int, seen: set):
        while words:  # the command itself, not its prefixes
            name = os.path.basename(words[0])
            if words[0] in KEYWORDS or ASSIGN_RE.match(words[0]):
                words.pop(0)
            elif words[0] == "function":
                words = words[2:]
            elif name in WRAPPERS:
                words = _unwrap(name, words[1:])
            else:
                break
        if not words:
            return None
        name, args = os.path.basename(words[0]), words[1:]
        items = self.listed(name, args, base)
        for w, spec, b in items if items is not None else [(a, False, base) for a in args]:
            if spec:
                found = self.probe_spec(w, b)
            elif not w.startswith("-"):
                found = self.probe(w, b, False, depth, seen)
            else:
                continue
            if found:
                return found
        return None

    def probe_spec(self, word: str, base: str):
        """A git pathspec: ``*`` crosses directories."""
        r = self.resolve(word, base)
        if r is None:
            return None
        path, is_glob = r
        f = self.frozen
        hit = f.match_glob(path, True, cross=True) if is_glob else f.match_path(path, True)
        return (hit, self.where(word, is_glob, not is_glob)) if hit else None

    def listed(self, name: str, args: list[str], base: str) -> list[tuple[str, bool, str]] | None:
        """The paths a lister reads, as (word, is a git pathspec, base), with ``.`` when it
        names none; None for any other command, whose plain arguments are all taken as possible
        paths."""
        if name == "find":
            i = 0
            while i < len(args) and (args[i] in ("-H", "-L", "-P") or args[i].startswith("-O")):
                i += 1
            starts = []
            while i < len(args) and not args[i].startswith("-") and args[i] not in ("(", "!"):
                starts.append(args[i])
                i += 1
            return [(s, False, base) for s in starts or ["."]]
        if name in GREPS or name in RGS:
            valued = GREP_VALUED if name in GREPS else RG_VALUED
            opts, pos = _split(args, valued)
            shorts = _shorts(opts)
            given = bool(shorts & {"e", "f"}) or any(
                o.startswith(("--regexp", "--file")) for o in opts
            )
            paths = pos if given else pos[1:]
            recursive = (
                name in RGS
                or bool(shorts & {"r", "R"})
                or any(
                    o.startswith(
                        ("--recursive", "--dereference-recursive", "--directories=recurse")
                    )
                    for o in opts
                )
            )
            return [(p, False, base) for p in paths or (["."] if recursive else [])]
        if name in FDS:
            _, pos = _split(args, FD_VALUED)
            return [(p, False, base) for p in pos[1:] or ["."]]
        if name == "ls":
            _, pos = _split(args, {"-I", "-w", "-T", "--ignore", "--width", "--tabsize"})
            return [(p, False, base) for p in pos or ["."]]
        if name == "git":
            i = 0
            while i < len(args) and args[i].startswith("-"):
                if args[i] in ("-C", "--work-tree") and i + 1 < len(args):
                    base = self._dir(args[i + 1], base)
                    i += 1
                elif args[i] in ("-c", "--git-dir", "--namespace"):
                    i += 1
                i += 1
            if i >= len(args) or args[i] not in GIT_LISTERS:
                return []
            sub, rest = args[i], args[i + 1 :]
            if "--" in rest:
                specs = rest[rest.index("--") + 1 :]
            else:
                opts, pos = _split(rest, {"-e", "-f", "--format", "--pretty", "-n", "-x"})
                if sub == "grep" and not ({"-e", "-f"} & set(opts)):
                    pos = pos[1:]  # the pattern
                specs = [p for p in pos if _has_glob(p) or self.exists(p, base)]
            return [(s, True, base) for s in specs or ["."]]
        return None

    def exists(self, word: str, base: str) -> bool:
        r = self.resolve(word, base)
        return r is not None and not r[1] and os.path.lexists(r[0])

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
        while i < len(args) and args[i][:1] in ("-", "+"):
            a = args[i]
            if a in ("-", "--"):  # end of options: the next word is the -c string
                i += 1
                break
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
                    base = self._dir(args[i + 1], base)
                i += 2
                continue
            if a.startswith("--work-tree="):
                base = self._dir(a.split("=", 1)[1], base)
            i += 1
        if i >= len(args):
            return
        cmd, rest = args[i], args[i + 1 :]
        if cmd == "clean":  # removes untracked (with -x also ignored) files under its pathspecs
            flags, _, pos = _gnu(rest, "e", {"--exclude"})
            if not flags & {"n", "--dry-run"}:
                for p in pos or ["."]:
                    self.target(p, base, recursive=True)
            return
        if cmd == "submodule":
            j = 0
            while j < len(rest) and rest[j].startswith("-"):
                j += 1
            if j < len(rest) and rest[j] == "deinit":  # empties the submodule's work tree
                flags, _, pos = _gnu(rest[j + 1 :])
                for p in pos or (["."] if "--all" in flags else []):
                    self.target(p, base, recursive=True)
            return
        valued = {
            "checkout": {"-b", "-B", "--orphan"},
            "restore": {"-s", "--source"},
            "rm": set(),
            "mv": set(),
        }.get(cmd)
        if valued is None:
            return
        opts, pos = _split(rest, valued)
        if cmd == "restore":  # --staged alone resets the index to HEAD and writes no file
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
                cmd = expr[j + 1 : k]
                under = [("value", s.rstrip("/") + "/**", base) for s in starts]
                ph = self.placeholder("find_path", under)  # {} is anything under a start path
                sub = [w.replace("{}", ph) for w in cmd]
                if sub:
                    name = os.path.basename(_unwrap("env", sub)[0] if sub[0] == "env" else sub[0])
                    if name in SHELLS or name == "eval":  # sh -c '... "$1"' _ {}
                        self.unknown(ph, base, True)
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
        if name in ("tar", "bsdtar", "gtar"):
            return self.tar(args)
        if name == "unzip":
            return self.unzip(args)
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
            return self.interpreter(name, args, base)
        return None

    def copy_like(self, name: str, args: list[str], base: str) -> list[tuple[str, bool]]:
        short, long_ = "tS", {"--target-directory", "--suffix"}
        if name == "install":
            short, long_ = short + "mog", long_ | {"--mode", "--owner", "--group"}
        flags, values, pos = _gnu(args, short, long_)
        tdirs = values.get("t", []) + values.get("--target-directory", [])
        if name == "install" and flags & {"d", "--directory"}:
            return [(p, False) for p in pos]
        tree = name == "mv" or (
            name == "cp" and bool(flags & {"r", "R", "a", "--recursive", "--archive"})
        )
        no_dir = bool(flags & {"T", "--no-target-directory"})
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

    @staticmethod
    def tar(args: list[str]) -> list[tuple[str, bool]] | None:
        if args and not args[0].startswith("-"):  # `tar xzf a.tar`: the first word bundles letters
            args = ["-" + args[0], *args[1:]]
        flags, values, pos = _gnu(args, "fCTXbHKNgILVF", TAR_LONG_VALUED)
        if flags & {"x", "--extract", "--get"}:
            if flags & {"O", "--to-stdout", "--to-command"}:
                return None
            dest = (values.get("C", []) + values.get("--directory", []) or ["."])[-1]
            if pos:  # named members land under the directory
                return [(dest.rstrip("/") + "/" + m, True) for m in pos]
            return [(dest, True)]
        if flags & {"c", "r", "u", "A", "--create", "--append", "--update", "--delete"}:
            files = values.get("f", []) + values.get("--file", [])
            return [(f, False) for f in files if f != "-"]
        return None

    @staticmethod
    def unzip(args: list[str]) -> list[tuple[str, bool]] | None:
        dest, pos, flags, exclude, i = ".", [], set(), False, 0
        while i < len(args):
            a = args[i]
            if a == "-x":
                exclude = True
            elif a.startswith("-") and len(a) > 1:
                exclude = False
                for j in range(1, len(a)):
                    if a[j] == "d":  # -d DIR / -dDIR: the extraction directory
                        if j + 1 < len(a):
                            dest = a[j + 1 :]
                        elif i + 1 < len(args):
                            i += 1
                            dest = args[i]
                        break
                    flags.add(a[j])
            elif not exclude:
                pos.append(a)
            i += 1
        if flags & set("lvtzZpc"):  # list, test, comment, pipe: nothing written
            return None
        members = pos[1:]
        if members:
            return [(dest.rstrip("/") + "/" + m, False) for m in members]
        return [(dest, True)]

    def interpreter(self, name: str, args: list[str], base: str) -> list[tuple[str, bool]] | None:
        if name.startswith("python"):
            i = 0
            while i < len(args):
                a = args[i]
                if a in ("-", "--") or not a.startswith("-"):
                    break  # a script, or stdin
                if a.startswith("--"):
                    i += 2 if a == "--check-hash-based-pycs" else 1
                    continue
                for j in range(1, len(a)):
                    ch, rest = a[j], a[j + 1 :]
                    if ch == "c":
                        code = rest or (args[i + 1] if i + 1 < len(args) else "")
                        self.code(code)
                        return None
                    if ch == "m":
                        mod = rest or (args[i + 1] if i + 1 < len(args) else "")
                        return self.module(mod, args[i + 1 :] if rest else args[i + 2 :], base)
                    if ch in "WX":  # the value is the rest of the word or the next word
                        i += 0 if rest else 1
                        break
                i += 1
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

    def module(self, mod: str, args: list[str], base: str) -> list[tuple[str, bool]] | None:
        """``python -m MOD ARGS``: formatters write as their commands do; zipfile/tarfile -e
        extract into a directory."""
        if mod in FORMATTERS or mod == "ruff":
            return self.writes(mod, args, base)
        if mod in ("zipfile", "tarfile"):
            for k, a in enumerate(args):
                if a in ("-e", "--extract"):
                    rest = args[k + 1 : k + 3]
                    return [(rest[1] if len(rest) > 1 else ".", True)]
        return None


def scan_bash(frozen: Frozen, command: str, cwd: str, root: str) -> list[tuple[str, str | None]]:
    env = dict(os.environ)
    env.setdefault("CLAUDE_PROJECT_DIR", root)
    scan = Scan(frozen, command, env)
    try:
        scan.script(command, cwd)
        scan.settle()
    except Exception as exc:  # a bug in the guard must not wedge the session
        print(
            f"deny_frozen: warning: internal error ({exc!r}); conservative check", file=sys.stderr
        )
        scan.fallback(command)
    return scan.hits


def _messages(hits: list[tuple[str, str | None]]) -> list[str]:
    return [REASON.format(h) + (f"\n  why: {why}" if why else "") for h, why in hits]


def check(payload: dict, root: str) -> list[str]:
    """The block messages for this tool call (empty: allow)."""
    root = os.path.abspath(root)
    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    if not isinstance(tool, str) or not isinstance(ti, dict):
        return []
    writes = tool == "Bash" or tool in FILE_TOOLS or bool(WRITEISH_TOOL.search(tool))
    if not writes:
        return []
    try:
        frozen = Frozen.load(root)
    except Unreadable as exc:
        return [UNREADABLE.format(exc)]
    if frozen is None or not frozen.patterns:
        return []
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) and os.path.isabs(cwd) else root
    if tool == "Bash":
        command = ti.get("command")
        return _messages(scan_bash(frozen, command, cwd, root)) if isinstance(command, str) else []
    hits = []
    for key in ("file_path", "notebook_path"):
        path = ti.get(key)
        if isinstance(path, str) and path:
            path = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
            hit = frozen.match_path(path)
            if hit:
                hits.append((hit, None))
    return _messages(hits)


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
        messages = check(payload, root)
    except Exception as exc:  # never wedge the session
        print(f"deny_frozen: warning: internal error ({exc!r}); allowed", file=sys.stderr)
        return 0
    for m in messages[:5]:
        print(m, file=sys.stderr)
    return 2 if messages else 0


if __name__ == "__main__":
    sys.exit(main())
