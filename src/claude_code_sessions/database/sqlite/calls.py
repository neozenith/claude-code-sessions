"""
Extraction of the ``event_calls`` raw fact table rows from a parsed event.

Five discriminated call types are produced:

* ``tool``     — any ``tool_use`` content block whose name isn't Skill/Agent.
* ``skill``    — ``tool_use`` where ``name == "Skill"``; call_name is ``input.skill``.
* ``subagent`` — ``tool_use`` where ``name == "Agent"``; call_name is ``input.subagent_type``.
* ``cli``      — command head parsed from each Bash ``input.command`` (additive
                 to the ``tool`` row emitted for the Bash call itself).
* ``rule``     — an absolute path extracted from ``Contents of <path>`` inside
                 a ``<system-reminder>`` block embedded in user-message text.

Extraction is a pure function of the raw event dict — no I/O, no SQL — so it
is trivial to unit-test and to mirror verbatim into the standalone introspect
script that shares the cache schema.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Regexes — compiled once at import time.
# ---------------------------------------------------------------------------

# Locate <system-reminder>...</system-reminder> blocks (non-greedy, dotall so
# newlines inside the reminder body are consumed).
_SYSTEM_REMINDER_RE = re.compile(
    r"<system-reminder>(.*?)</system-reminder>",
    re.DOTALL,
)

# Extract absolute paths following "Contents of " inside a system-reminder.
# This matches the canonical format used by Claude Code to inject CLAUDE.md
# and .claude/rules/*.md files into the conversation. The character class
# excludes whitespace AND ``:`` so the trailing colon ("Contents of /foo.md:")
# is not captured into the call_name — and neither are quote characters
# from paths embedded inside quoted strings.
_RULE_PATH_RE = re.compile(r"Contents of\s+(/[^\s:'\"]+)")

# Shell separators that start a new command segment in an input.command
# string. Order matters only to the extent that ``re.split`` consumes all
# alternations at once — each alternation must be a distinct literal.
_SHELL_SPLIT_RE = re.compile(r"\|\||&&|;|\|")

# Command "wrappers" whose first positional argument is itself a command.
# We skip past them (and any of their flags) to find the real program head.
_WRAPPERS: frozenset[str] = frozenset({
    "sudo", "time", "nohup", "exec", "xargs", "env", "command",
})

# Bash control-flow keywords that INTRODUCE a command. A segment like
# ``do cmd`` really invokes ``cmd`` — the ``do`` is syntactic scaffolding
# from a surrounding for/while/until loop that survived the segment
# splitter. Unwrapping them behaves like ``_WRAPPERS`` but without flag
# consumption (these keywords don't take ``-flags``).
_SHELL_KEYWORDS_UNWRAP: frozenset[str] = frozenset({
    "if", "elif", "then", "else", "do", "while", "until",
})

# Bash tokens that, when appearing as the first non-env word, mean the
# segment carries no real command — either a loop header (``for i in …``,
# ``case X in``) or a block terminator (``done``, ``fi``, ``esac``).
_SHELL_SEGMENT_REJECT: frozenset[str] = frozenset({
    "for", "case", "in",
    "done", "fi", "esac",
})

# GNU make flags that take a following positional argument. When parsing
# ``make <target>`` segments we need to skip past these flag+arg pairs so
# the arg isn't misread as a target name (e.g. ``make -C subproject test``
# has target ``test``, not ``subproject``).
_MAKE_FLAGS_WITH_ARG: frozenset[str] = frozenset({
    "-C", "-f", "-I", "-j", "-l", "-o", "-W",
})


# ---------------------------------------------------------------------------
# CLI head parsing
# ---------------------------------------------------------------------------

def _parse_cli_segments(command: str) -> list[tuple[str, list[str]]]:
    """Parse a shell command into ``(head, post_head_tokens)`` segments.

    Each returned tuple is one sub-command: the program name and the
    remaining tokens (arguments, flags) in order. Wrapper commands like
    ``sudo`` are skipped and the wrapped program is returned as the head.

    Examples
    --------
    >>> _parse_cli_segments("gh pr view 42")
    [('gh', ['pr', 'view', '42'])]
    >>> _parse_cli_segments("aws s3 ls | grep foo")
    [('aws', ['s3', 'ls']), ('grep', ['foo'])]
    >>> _parse_cli_segments("sudo -E make test")
    [('make', ['test'])]
    """
    if not command:
        return []

    out: list[tuple[str, list[str]]] = []
    for segment in _SHELL_SPLIT_RE.split(command):
        tokens = segment.strip().split()
        result = _segment_head_and_rest(tokens)
        if result is not None:
            out.append(result)
    return out


def _parse_cli_heads(command: str) -> list[str]:
    """Return the program-name head(s) of each sub-command in a shell string.

    Thin wrapper over ``_parse_cli_segments`` for callers that only care
    about the heads (backwards compatibility with the original API).
    """
    return [head for head, _rest in _parse_cli_segments(command)]


def _parse_make_targets(tokens_after_make: list[str]) -> list[str]:
    """Extract the target names from tokens appearing after ``make``.

    Skips flags (``-j``, ``-s``, ``--silent``…) and the positional
    arguments consumed by known flag-with-arg pairs (``-C dir``,
    ``-f Makefile``, etc.). Also skips ``VAR=value`` overrides. The rest
    are treated as target names.

    Examples
    --------
    >>> _parse_make_targets(['test'])
    ['test']
    >>> _parse_make_targets(['-C', 'subproject', 'test'])
    ['test']
    >>> _parse_make_targets(['test', 'format'])
    ['test', 'format']
    >>> _parse_make_targets(['CI=true', '-j', '4', 'ci'])
    ['ci']
    >>> _parse_make_targets(['--directory=subproj', 'build'])
    ['build']
    """
    targets: list[str] = []
    i = 0
    while i < len(tokens_after_make):
        tok = tokens_after_make[i]
        if tok.startswith("--"):
            # Long-form flag. `--directory=subproj` is self-contained;
            # `--jobs 4` would need a lookahead, but such forms are rare
            # in practice. Skip a single token either way.
            i += 1
            continue
        if tok in _MAKE_FLAGS_WITH_ARG:
            # Consume the flag plus its argument.
            i += 2
            continue
        if tok.startswith("-"):
            # Other short flag (no arg), e.g. `-s`, `-k`, `-n`.
            i += 1
            continue
        if _is_env_assignment(tok):
            # Make variable override (`CI=true`) — not a target.
            i += 1
            continue
        if _is_shell_redirection(tok):
            # `2>&1`, `&`, `>log`, etc. — shell artifacts that slipped
            # past the segment splitter (common in `make test 2>&1 | tee`).
            # Never a target.
            i += 1
            continue
        targets.append(tok)
        i += 1
    return targets


def _is_shell_redirection(tok: str) -> bool:
    """True for shell redirection / control tokens like ``2>&1``, ``&``, ``>log``.

    Remaining forms we haven't split on upstream:

    - ``&``                 — background the command
    - ``>``, ``>>``, ``<``  — redirection operators (standalone or ``>file``)
    - ``2>``, ``2>&1``, ``2>>file`` — stderr redirection (fd prefix)
    """
    if not tok:
        return False
    first = tok[0]
    if first in "<>&":
        return True
    # fd-prefixed forms like `1>`, `2>>`, `2>&1`.
    if first.isdigit() and len(tok) > 1 and tok[1] in "<>":
        return True
    return False


def _segment_head_and_rest(tokens: list[str]) -> tuple[str, list[str]] | None:
    """Skip env-var assignments and wrappers, return ``(head, rest)``.

    ``rest`` is the slice of ``tokens`` after the head — i.e. the
    arguments and flags passed to the program. Returns ``None`` when the
    segment is empty, contains only env assignments/wrappers, or begins
    with a bash control-flow token that means "no real command here".
    """
    i = 0

    # Skip KEY=VALUE env assignments at the start of a segment.
    while i < len(tokens) and _is_env_assignment(tokens[i]):
        i += 1

    # Reject segments that are purely bash control structure (loop
    # headers like `for i in LIST`, block terminators like `done`/`fi`).
    # These appear as their own segments after splitting on `;` and
    # have no meaningful command to record.
    if i < len(tokens) and tokens[i] in _SHELL_SEGMENT_REJECT:
        return None

    # Unwrap shell control keywords that INTRODUCE a command:
    # `do cmd`, `then cmd`, `while cond`, etc. The real invocation is
    # whatever comes next. No flag-consumption pass because these
    # keywords don't take options.
    while i < len(tokens) and tokens[i] in _SHELL_KEYWORDS_UNWRAP:
        i += 1

    # Re-check the rejection list after keyword unwrap (handles nested
    # combos like `do done` which would degenerate to nothing).
    if i < len(tokens) and tokens[i] in _SHELL_SEGMENT_REJECT:
        return None

    # Unwrap sudo/time/nohup/xargs/env/... recursively.
    while i < len(tokens) and tokens[i] in _WRAPPERS:
        i += 1
        # Consume wrapper flags (e.g. ``sudo -E``, ``xargs -P 4 -n 1``).
        while i < len(tokens) and tokens[i].startswith("-"):
            i += 1
        # ``env`` can be followed by additional KEY=VALUE assignments.
        while i < len(tokens) and _is_env_assignment(tokens[i]):
            i += 1

    if i >= len(tokens):
        return None

    raw = tokens[i]
    # Strip a leading shell substitution/grouping character like "(".
    raw = raw.lstrip("(")
    # Basename: /usr/bin/gh → gh
    raw = raw.rsplit("/", 1)[-1]
    # Drop trailing shell metacharacters stuck to the word.
    raw = raw.rstrip("();&")
    if not raw:
        return None
    # Reject heads that are pure punctuation — bare quotes, semicolons,
    # and other shell metacharacters that sometimes survive tokenisation
    # of multi-line heredocs or `sh -c "..."` arguments. A real command
    # name always contains at least one letter or digit.
    if not any(c.isalnum() for c in raw):
        return None
    return raw, tokens[i + 1:]


def _head_of_segment(tokens: list[str]) -> str | None:
    """Return just the head of a segment (kept for internal call sites)."""
    result = _segment_head_and_rest(tokens)
    return result[0] if result else None


def _is_env_assignment(token: str) -> bool:
    """True for tokens of the form ``NAME=value`` (valid env var assignment)."""
    if "=" not in token or token.startswith("-") or token.startswith("="):
        return False
    name, _, _ = token.partition("=")
    if not name:
        return False
    # POSIX env var names: letters, digits, underscore; cannot start with digit.
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in name)


# ---------------------------------------------------------------------------
# Rule-path parsing
# ---------------------------------------------------------------------------

def _extract_rule_paths(text: str) -> list[str]:
    """Return every rule-file path cited in <system-reminder> blocks in ``text``."""
    paths: list[str] = []
    for reminder in _SYSTEM_REMINDER_RE.findall(text):
        for match in _RULE_PATH_RE.finditer(reminder):
            paths.append(match.group(1))
    return paths


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def extract_calls(raw: dict[str, Any]) -> list[tuple[int, str, str]]:
    """Return ``(ord, call_type, call_name)`` rows for an event's signals.

    ``ord`` is the position of the source content block (or zero for rule
    rows derived from embedded text). Order within an event is preserved so
    downstream queries can reconstruct the sequence of actions faithfully.
    """
    calls: list[tuple[int, str, str]] = []
    message = raw.get("message") if isinstance(raw, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return calls

    for idx, block in enumerate(content):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_use":
            calls.extend(_extract_tool_use(idx, block))
        elif block_type == "text":
            text = block.get("text") or ""
            for path in _extract_rule_paths(text):
                calls.append((idx, "rule", path))
    return calls


def _extract_tool_use(idx: int, block: dict[str, Any]) -> list[tuple[int, str, str]]:
    """Extract rows for a single tool_use content block."""
    name = block.get("name") or ""
    raw_input = block.get("input")
    inp: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
    rows: list[tuple[int, str, str]] = []

    if name == "Skill":
        skill_val = inp.get("skill")
        skill = skill_val.strip() if isinstance(skill_val, str) else ""
        if skill:
            rows.append((idx, "skill", skill))
        else:
            # Fallback: still count the tool_use even if input is malformed.
            rows.append((idx, "tool", name))
        return rows

    if name == "Agent":
        subagent_val = inp.get("subagent_type")
        subagent = subagent_val.strip() if isinstance(subagent_val, str) else ""
        if subagent:
            rows.append((idx, "subagent", subagent))
        else:
            rows.append((idx, "tool", name))
        return rows

    if name:
        rows.append((idx, "tool", name))

    if name == "Bash":
        command_val = inp.get("command")
        command = command_val if isinstance(command_val, str) else ""
        # Walk each pipeline/chain segment once. For every segment we
        # emit one 'cli' row (the head) plus, when the head is `make`,
        # one 'make_target' row per target. A command like
        # `make test && make lint format` yields:
        #   cli=make, make_target=test, cli=make,
        #   make_target=lint, make_target=format
        for head, rest in _parse_cli_segments(command):
            rows.append((idx, "cli", head))
            if head == "make":
                for target in _parse_make_targets(rest):
                    rows.append((idx, "make_target", target))

    return rows
