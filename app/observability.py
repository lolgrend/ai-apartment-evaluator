"""Langfuse tracing helpers for application-level context."""
from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager, nullcontext
from functools import lru_cache
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 1_200
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()
    if "LANGFUSE_BASE_URL" not in os.environ and "LANGFUSE_HOST" in os.environ:
        os.environ["LANGFUSE_BASE_URL"] = os.environ["LANGFUSE_HOST"]


def _has_credentials() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
        and (os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST"))
    )


@lru_cache
def _langfuse_client() -> Any | None:
    _load_env()
    if not _has_credentials():
        return None
    try:
        from langfuse import get_client
    except ImportError:
        logger.info("Langfuse credentials are configured but the langfuse package is not installed.")
        return None
    try:
        return get_client()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to initialize Langfuse client.")
        return None


def enabled() -> bool:
    return _langfuse_client() is not None


def _clean_attrs(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value is not None and value != "" and value != []
    }


def redact_text(value: str | None, *, limit: int = _MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    text = _EMAIL_RE.sub("[email]", value)
    text = _PHONE_RE.sub("[phone]", text)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated {len(text) - limit} chars]"


def _content_summary(content: Any) -> dict[str, Any]:
    if isinstance(content, str):
        return {"type": "text", "text": redact_text(content)}
    if not isinstance(content, list):
        return {"type": type(content).__name__}

    text_parts = []
    image_count = 0
    other_types: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            other_types.append(type(part).__name__)
            continue
        part_type = part.get("type")
        if part_type == "text":
            text_parts.append(str(part.get("text") or ""))
        elif part_type == "image_url":
            image_count += 1
        elif part_type:
            other_types.append(str(part_type))
    return _clean_attrs({
        "type": "parts",
        "text": redact_text("\n".join(text_parts)),
        "image_count": image_count,
        "other_types": other_types,
    })


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages") or []
    summarized_messages = []
    if isinstance(messages, list):
        for message in messages[-4:]:
            if not isinstance(message, dict):
                continue
            summarized_messages.append(_clean_attrs({
                "role": message.get("role"),
                "content": _content_summary(message.get("content")),
                "tool_calls": len(message.get("tool_calls") or []),
                "name": message.get("name"),
            }))

    tools = payload.get("tools") or []
    tool_names = []
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict):
                function = tool.get("function") or {}
                if isinstance(function, dict) and function.get("name"):
                    tool_names.append(function["name"])

    return _clean_attrs({
        "model": payload.get("model"),
        "max_completion_tokens": payload.get("max_completion_tokens"),
        "response_format": (payload.get("response_format") or {}).get("type")
        if isinstance(payload.get("response_format"), dict) else None,
        "tool_choice": payload.get("tool_choice"),
        "tools": tool_names,
        "messages": summarized_messages,
    })


def summarize_response(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    first_message = {}
    if choices and isinstance(choices[0], dict):
        first_message = choices[0].get("message") or {}
    return _clean_attrs({
        "content": redact_text(first_message.get("content")),
        "tool_calls": len(first_message.get("tool_calls") or []),
        "finish_reason": choices[0].get("finish_reason")
        if choices and isinstance(choices[0], dict) else None,
    })


def usage_details(response: dict[str, Any]) -> dict[str, Any]:
    usage = response.get("usage") or {}
    if not isinstance(usage, dict):
        return {}
    return _clean_attrs({
        "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    })


@contextmanager
def trace_operation(
    name: str,
    *,
    user_id: str | int | None = None,
    session_id: str | None = None,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Iterator[Any | None]:
    client = _langfuse_client()
    if client is None:
        yield None
        return

    try:
        from langfuse import propagate_attributes
    except ImportError:
        yield None
        return

    attrs = _clean_attrs({
        "user_id": str(user_id) if user_id is not None else None,
        "session_id": session_id,
        "metadata": metadata,
        "tags": tags,
        "trace_name": name,
    })
    try:
        with client.start_as_current_observation(
            as_type="span",
            name=name,
            input=input_data,
        ) as span:
            with propagate_attributes(**attrs):
                yield span
    except Exception:
        raise


@contextmanager
def trace_generation(
    name: str,
    *,
    model: str | None,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any | None]:
    client = _langfuse_client()
    if client is None:
        yield None
        return

    try:
        context = client.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input_data,
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start Langfuse generation.")
        context = nullcontext(None)
    with context as generation:
        yield generation


@contextmanager
def trace_guardrail(
    name: str,
    *,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any | None]:
    client = _langfuse_client()
    if client is None:
        yield None
        return

    try:
        context = client.start_as_current_observation(
            as_type="guardrail",
            name=name,
            input=input_data,
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start Langfuse guardrail observation.")
        context = nullcontext(None)
    with context as guardrail:
        yield guardrail


def flush() -> None:
    client = _langfuse_client()
    if client is not None:
        client.flush()
