#!/usr/bin/env python3
"""Extract Open Design <question-form> blocks from text or od run NDJSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any


OPEN_RE = re.compile(r"<(question-form|ask-question)\b([^>]*)>", re.IGNORECASE)


def parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"(\w+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", raw):
        attrs[match.group(1)] = unescape(match.group(2) or match.group(3) or "")
    return attrs


def text_from_input(raw: str) -> str:
    chunks: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            chunks.append(line)
            continue
        data = event.get("data") if isinstance(event, dict) else None
        if isinstance(data, str):
            chunks.append(data)
        elif isinstance(data, dict):
            if data.get("type") == "text_delta" and isinstance(data.get("delta"), str):
                chunks.append(data["delta"])
            elif isinstance(data.get("content"), str):
                chunks.append(data["content"])
            elif isinstance(data.get("line"), str):
                chunks.append(data["line"])
    return "\n".join(chunks) if chunks else raw


def strip_fence(body: str) -> str:
    body = body.strip()
    body = re.sub(r"^```(?:json)?\s*", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\s*```$", "", body)
    return body.strip()


def extract_forms(text: str) -> list[dict[str, Any]]:
    forms: list[dict[str, Any]] = []
    cursor = 0
    while True:
        match = OPEN_RE.search(text, cursor)
        if not match:
            break
        tag = match.group(1).lower()
        close_re = re.compile(rf"</{re.escape(tag)}>", re.IGNORECASE)
        close = close_re.search(text, match.end())
        if not close:
            break
        body = text[match.end():close.start()]
        attrs = parse_attrs(match.group(2) or "")
        try:
            parsed = json.loads(strip_fence(body))
        except json.JSONDecodeError:
            cursor = close.end()
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
            form = {
                "id": attrs.get("id") or parsed.get("id") or "discovery",
                "title": attrs.get("title") or parsed.get("title") or "A few quick questions",
                "questions": parsed["questions"],
                "raw": text[match.start():close.end()],
            }
            if isinstance(parsed.get("description"), str):
                form["description"] = parsed["description"]
            forms.append(form)
        cursor = close.end()
    return forms


def option_label(option: Any) -> str:
    if isinstance(option, str):
        return option
    if isinstance(option, dict):
        label = option.get("label") or option.get("value")
        if isinstance(label, str):
            return label
    return str(option)


def template_for(form: dict[str, Any]) -> str:
    lines = [f"[form answers - {form.get('id', 'discovery')}]"]
    for q in form.get("questions", []):
        if not isinstance(q, dict):
            continue
        label = q.get("label") or q.get("id") or "Question"
        options = q.get("options")
        suffix = ""
        if isinstance(options, list) and options:
            suffix = "  # options: " + ", ".join(option_label(o) for o in options[:8])
        lines.append(f"- {label}: {suffix}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="Input file. Reads stdin when omitted or '-'.")
    parser.add_argument("--all", action="store_true", help="Print all forms instead of only the last form.")
    parser.add_argument("--template", action="store_true", help="Print a form-answer template.")
    args = parser.parse_args()

    if not args.path or args.path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.path).read_text(encoding="utf-8")

    forms = extract_forms(text_from_input(raw))
    if not forms:
        print("No question-form found.", file=sys.stderr)
        return 1

    selected = forms if args.all else [forms[-1]]
    if args.template:
        print("\n\n".join(template_for(form) for form in selected))
    else:
        payload: Any = selected if args.all else selected[0]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
