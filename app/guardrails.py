"""Simple runtime checks for low-effort prompt injection attempts."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardrailResult:
    is_blocked: bool
    risk_score: float
    matched_rules: list[str]


_RULES: list[tuple[str, re.Pattern[str], float]] = [
    (
        "ignore_previous_instructions",
        re.compile(
            r"\b(ignore|forget|disregard|override)\b.{0,80}\b"
            r"(previous|prior|all|above|system|developer)\b.{0,80}\b"
            r"(instructions?|prompts?|rules?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        0.55,
    ),
    (
        "polish_ignore_previous_instructions",
        re.compile(
            r"\b(zignoruj|zapomnij|pomiń|nadpisz)\b.{0,80}\b"
            r"(poprzednie|wcześniejsze|wszystkie|systemowe)\b.{0,80}\b"
            r"(instrukcje|polecenia|zasady|prompt)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        0.55,
    ),
    (
        "system_prompt_exfiltration",
        re.compile(
            r"\b(reveal|show|print|dump|repeat|exfiltrate|leak|wyświetl|pokaż|ujawnij|wypisz)\b"
            r".{0,100}\b(system prompt|developer message|hidden instructions|prompt systemowy|ukryte instrukcje)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        0.7,
    ),
    (
        "roleplay_jailbreak",
        re.compile(
            r"\b(you are now|act as|pretend to be|jesteś teraz|udawaj)\b.{0,80}\b"
            r"(dan|jailbreak|bez ograniczeń|without restrictions|no rules)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        0.45,
    ),
    (
        "tool_data_exfiltration",
        re.compile(
            r"\b(call|use|invoke|użyj|wywołaj)\b.{0,80}\b(get_listing_details)\b"
            r".{0,120}\b(all|every|wszystkie|całą bazę|sekrety|secrets?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        0.45,
    ),
]

_BLOCK_THRESHOLD = 0.7


def check_prompt_injection(text: str | None) -> GuardrailResult:
    if not text:
        return GuardrailResult(False, 0.0, [])

    matched: list[str] = []
    risk_score = 0.0
    for name, pattern, weight in _RULES:
        if pattern.search(text):
            matched.append(name)
            risk_score += weight

    risk_score = min(risk_score, 1.0)
    return GuardrailResult(
        is_blocked=risk_score >= _BLOCK_THRESHOLD,
        risk_score=risk_score,
        matched_rules=matched,
    )
