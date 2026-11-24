"""User vocabulary: names and terms the recogniser tends to get wrong.

One entry is a term spelled the way it must appear, plus optional "sounds
like" spellings a transcript may show instead. It is used in three places:

* after recognition, every "sounds like" spelling (and the term in the wrong
  letter case) is replaced by the term — works for any engine, no LLM needed;
* Whisper gets the terms as its initial prompt, which biases recognition
  (Parakeet has no such input);
* the AI post-processing prompt lists the terms, so the model restores
  inflected or otherwise mangled forms the plain replacement cannot match.

Config key ``vocabulary``: ``[{"term": str, "sounds_like": [str, …]}, …]``.
The settings window edits it as text, one entry per line:
``Kubernetes: кубернетес, кубернетис``.
"""
from __future__ import annotations

import re

MAX_TERMS = 300
MAX_LEN = 64            # characters per term / spelling
WHISPER_PROMPT_CHARS = 600


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:MAX_LEN]


def normalize(raw) -> list[dict]:
    """Valid entries from whatever the config holds (bad items are dropped)."""
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"term": item}
        if not isinstance(item, dict):
            continue
        term = _clean(item.get("term"))
        if not term or term.casefold() in seen:
            continue
        seen.add(term.casefold())
        variants = item.get("sounds_like") or []
        if isinstance(variants, str):
            variants = variants.split(",")
        spellings: list[str] = []
        for v in variants:
            v = _clean(v)
            if v and v.casefold() != term.casefold() and v.casefold() not in {s.casefold() for s in spellings}:
                spellings.append(v)
        out.append({"term": term, "sounds_like": spellings})
        if len(out) >= MAX_TERMS:
            break
    return out


def from_config(data: dict) -> list[dict]:
    return normalize((data or {}).get("vocabulary"))


def parse_text(text: str) -> list[dict]:
    """Entries from the editor format: ``Term: spelling, spelling`` per line."""
    raw = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        term, _, variants = line.partition(":")
        raw.append({"term": term, "sounds_like": variants.split(",")})
    return normalize(raw)


def to_text(entries: list[dict]) -> str:
    lines = []
    for e in normalize(entries):
        lines.append(e["term"] + (": " + ", ".join(e["sounds_like"]) if e["sounds_like"] else ""))
    return "\n".join(lines)


def apply(text: str, entries: list[dict]) -> str:
    """Replace every "sounds like" spelling, and the term in another letter
    case, by the term. Whole words only, case-insensitive, longest first."""
    if not text or not entries:
        return text
    table: dict[str, str] = {}
    for e in entries:
        for spelling in [e["term"], *e["sounds_like"]]:
            table.setdefault(spelling.casefold(), e["term"])
    if not table:
        return text
    alternatives = sorted(table, key=len, reverse=True)
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(a) for a in alternatives) + r")(?!\w)",
        re.IGNORECASE | re.UNICODE)
    return pattern.sub(lambda m: table.get(m.group(1).casefold(), m.group(1)), text)


def whisper_prompt(entries: list[dict]) -> str:
    """Terms as Whisper's initial prompt (as many as fit its budget)."""
    picked: list[str] = []
    size = 0
    for e in entries:
        size += len(e["term"]) + 2
        if size > WHISPER_PROMPT_CHARS:
            break
        picked.append(e["term"])
    return ", ".join(picked)


def prompt_note(entries: list[dict]) -> str:
    """A paragraph for the AI post-processing prompt, or '' without entries."""
    if not entries:
        return ""
    items = []
    for e in entries:
        heard = f" (may be heard as: {', '.join(e['sounds_like'])})" if e["sounds_like"] else ""
        items.append(f"- {e['term']}{heard}")
    return ("Vocabulary. When the transcript contains one of these names or terms, "
            "possibly misheard or inflected, write it exactly as spelled here "
            "(keep the grammatical ending the sentence needs):\n" + "\n".join(items))
