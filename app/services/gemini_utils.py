"""Shared utilities for Gemini API response parsing."""

import json


def strip_fenced_block(text):
    """Remove markdown fenced code block wrappers from text."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_json(text):
    """Extract a JSON object from Gemini response text."""
    if not text:
        return None
    cleaned = strip_fenced_block(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def extract_text(payload):
    """Extract text content from a Gemini API response payload."""
    if not isinstance(payload, dict):
        return None
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        if not isinstance(content, dict):
            continue
        parts = content.get("parts") or []
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                return part.get("text")
    return None
