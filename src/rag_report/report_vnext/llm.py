from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from openai import OpenAI

from src.rag_report.config import settings
from src.rag_report.report_vnext.models import TaskType


RECOVERABLE_STATUS_CODES = {408, 409, 500, 502, 503, 504}
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_FIRST_TOKEN_DEADLINE_SECONDS = 45.0
_LLM_CALL_LOG: list[dict[str, Any]] = []


@dataclass(frozen=True)
class TaskModelConfig:
    task_type: TaskType
    model: str
    api_key: str
    base_url: str


@dataclass(frozen=True)
class LLMCallMetadata:
    task_type: str | None
    model: str
    base_url: str | None
    attempts: int
    retries: int
    finish_reason: str
    content_length: int
    stream: bool
    cancelled_due_to_deadline: bool
    first_token_deadline_seconds: float
    debug_label: str | None = None
    error_type: str | None = None


def reset_llm_call_log() -> None:
    _LLM_CALL_LOG.clear()


def get_llm_call_log() -> list[dict[str, Any]]:
    return [dict(item) for item in _LLM_CALL_LOG]


def _record_llm_call(metadata: LLMCallMetadata) -> None:
    _LLM_CALL_LOG.append(asdict(metadata))


def get_task_model_config(task_type: TaskType) -> TaskModelConfig:
    mapping = {
        "planner": TaskModelConfig(
            task_type="planner",
            model=settings.PLANNER_MODEL,
            api_key=settings.PLANNER_API_KEY,
            base_url=settings.PLANNER_API_BASE,
        ),
        "extraction": TaskModelConfig(
            task_type="extraction",
            model=settings.EXTRACTION_MODEL,
            api_key=settings.EXTRACTION_API_KEY,
            base_url=settings.EXTRACTION_API_BASE,
        ),
        "financial_reasoning": TaskModelConfig(
            task_type="financial_reasoning",
            model=settings.FINANCIAL_REASONING_MODEL,
            api_key=settings.FINANCIAL_REASONING_API_KEY,
            base_url=settings.FINANCIAL_REASONING_API_BASE,
        ),
        "chart_planning": TaskModelConfig(
            task_type="chart_planning",
            model=settings.CHART_PLANNING_MODEL,
            api_key=settings.CHART_PLANNING_API_KEY,
            base_url=settings.CHART_PLANNING_API_BASE,
        ),
    }
    return mapping[task_type]


def get_llm_client(task_type: TaskType) -> tuple[OpenAI, TaskModelConfig]:
    config = get_task_model_config(task_type)
    if not config.api_key:
        raise ValueError(f"Missing API key for task type '{task_type}'.")
    if not config.base_url:
        raise ValueError(f"Missing base_url for task type '{task_type}'.")
    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    return client, config


def _log_llm_attempt(
    *,
    task_type: str | None,
    model: str,
    base_url: str | None,
    attempt: int,
    finish_reason: object,
    content_length: int,
    cancelled_due_to_deadline: bool = False,
    debug_label: str | None = None,
) -> None:
    label = debug_label or task_type or "llm"
    print(
        "[llm] "
        f"{label} "
        f"task_type={task_type or 'unknown'} "
        f"model={model} "
        f"base_url={base_url or 'unknown'} "
        f"attempt={attempt} "
        f"retries={max(0, attempt - 1)} "
        f"finish_reason={finish_reason} "
        f"content_length={content_length} "
        f"cancelled_due_to_deadline={cancelled_due_to_deadline}",
        flush=True,
    )


def _first_choice(response: Any) -> Any | None:
    choices = getattr(response, "choices", None)
    if choices is None:
        return None
    try:
        return choices[0]
    except Exception:
        return None


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        parts: list[str] = []
        for item in content:
            text_value = getattr(item, "text", None)
            if text_value:
                parts.append(str(text_value))
        return "".join(parts)
    return ""


def _extract_text_from_response(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    output_text = getattr(response, "output_text", None)
    if output_text is not None:
        return str(output_text).strip()
    choice = _first_choice(response)
    if choice is None:
        return ""
    message = getattr(choice, "message", None)
    if not message:
        return ""
    return _extract_text_from_content(getattr(message, "content", "")).strip()


def _extract_text_from_stream_chunk(chunk: Any) -> str:
    choice = _first_choice(chunk)
    if choice is None:
        return ""
    delta = getattr(choice, "delta", None)
    if delta is not None:
        content = getattr(delta, "content", None)
        if content is not None:
            return _extract_text_from_content(content)
    message = getattr(choice, "message", None)
    if message is not None:
        return _extract_text_from_content(getattr(message, "content", ""))
    return _extract_text_from_response(chunk)


def _finish_reason_from_response(response: Any) -> str | None:
    choice = _first_choice(response)
    if choice is None:
        return None
    finish_reason = getattr(choice, "finish_reason", None)
    return str(finish_reason) if finish_reason is not None else None


def _is_timeout_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return "timeout" in name or "deadline" in name


def _is_recoverable_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {401, 403, 429, 402}:
        return False
    if status_code in RECOVERABLE_STATUS_CODES:
        return True
    if _is_timeout_error(exc):
        return True
    if status_code is None:
        return True
    return False


def _stream_llm_completion(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    *,
    task_type: str | None,
    base_url: str | None,
    debug: bool,
    debug_label: str | None,
    first_token_deadline_seconds: float,
    **kwargs: Any,
) -> tuple[str, str, bool]:
    request_kwargs = dict(kwargs)
    request_kwargs.setdefault("timeout", first_token_deadline_seconds)
    request_kwargs["stream"] = True
    response = None
    text_parts: list[str] = []
    finish_reason = "empty"
    cancelled_due_to_deadline = False
    start_time = time.monotonic()
    first_text_seen = False
    try:
        response = client.chat.completions.create(model=model, messages=messages, **request_kwargs)
        for chunk in response:
            if not first_text_seen and time.monotonic() - start_time > first_token_deadline_seconds:
                cancelled_due_to_deadline = True
                finish_reason = "timeout"
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                break
            chunk_text = _extract_text_from_stream_chunk(chunk)
            if chunk_text:
                text_parts.append(chunk_text)
                first_text_seen = True
            chunk_finish_reason = _finish_reason_from_response(chunk)
            if chunk_finish_reason:
                finish_reason = chunk_finish_reason
        if not text_parts and not cancelled_due_to_deadline and time.monotonic() - start_time > first_token_deadline_seconds:
            cancelled_due_to_deadline = True
            finish_reason = "timeout"
        text = "".join(text_parts).strip()
        if text and finish_reason == "empty":
            finish_reason = "stop"
        if debug:
            _log_llm_attempt(
                task_type=task_type,
                model=model,
                base_url=base_url,
                attempt=1,
                finish_reason=finish_reason,
                content_length=len(text),
                cancelled_due_to_deadline=cancelled_due_to_deadline,
                debug_label=debug_label,
            )
        return text, finish_reason, cancelled_due_to_deadline
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def call_llm_until_nonempty(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    *,
    sleep_seconds: float = 1.5,
    max_attempts: int | None = None,
    task_type: str | None = None,
    base_url: str | None = None,
    debug: bool = False,
    debug_label: str | None = None,
    stream: bool = True,
    first_token_deadline_seconds: float = DEFAULT_FIRST_TOKEN_DEADLINE_SECONDS,
    **kwargs: Any,
) -> str:
    attempts_limit = DEFAULT_MAX_ATTEMPTS if max_attempts is None else max(1, max_attempts)
    attempts = 0
    cancelled_due_to_deadline = False
    finish_reason = "empty"
    text = ""
    while attempts < attempts_limit:
        attempts += 1
        try:
            if stream:
                text, finish_reason, attempt_cancelled = _stream_llm_completion(
                    client,
                    model,
                    messages,
                    task_type=task_type,
                    base_url=base_url,
                    debug=debug,
                    debug_label=debug_label,
                    first_token_deadline_seconds=first_token_deadline_seconds,
                    **kwargs,
                )
                cancelled_due_to_deadline = cancelled_due_to_deadline or attempt_cancelled
            else:
                response = client.chat.completions.create(model=model, messages=messages, **kwargs)
                text = _extract_text_from_response(response)
                finish_reason = _finish_reason_from_response(response) or ("stop" if text else "empty")
                cancelled_due_to_deadline = False
                if debug:
                    _log_llm_attempt(
                        task_type=task_type,
                        model=model,
                        base_url=base_url,
                        attempt=attempts,
                        finish_reason=finish_reason,
                        content_length=len(text),
                        cancelled_due_to_deadline=False,
                        debug_label=debug_label,
                    )
        except Exception as exc:
            finish_reason = f"error:{type(exc).__name__}"
            cancelled_due_to_deadline = cancelled_due_to_deadline or _is_timeout_error(exc)
            if debug:
                _log_llm_attempt(
                    task_type=task_type,
                    model=model,
                    base_url=base_url,
                    attempt=attempts,
                    finish_reason=finish_reason,
                    content_length=0,
                    cancelled_due_to_deadline=cancelled_due_to_deadline,
                    debug_label=debug_label,
                )
            if _is_recoverable_error(exc) and attempts < attempts_limit:
                time.sleep(sleep_seconds)
                continue
            _record_llm_call(
                LLMCallMetadata(
                    task_type=task_type,
                    model=model,
                    base_url=base_url,
                    attempts=attempts,
                    retries=max(0, attempts - 1),
                    finish_reason=finish_reason,
                    content_length=0,
                    stream=stream,
                    cancelled_due_to_deadline=cancelled_due_to_deadline,
                    first_token_deadline_seconds=first_token_deadline_seconds,
                    debug_label=debug_label,
                    error_type=type(exc).__name__,
                )
            )
            return ""

        if text:
            _record_llm_call(
                LLMCallMetadata(
                    task_type=task_type,
                    model=model,
                    base_url=base_url,
                    attempts=attempts,
                    retries=max(0, attempts - 1),
                    finish_reason=finish_reason,
                    content_length=len(text),
                    stream=stream,
                    cancelled_due_to_deadline=cancelled_due_to_deadline,
                    first_token_deadline_seconds=first_token_deadline_seconds,
                    debug_label=debug_label,
                )
            )
            return text

        if attempts < attempts_limit:
            time.sleep(sleep_seconds)

    _record_llm_call(
        LLMCallMetadata(
            task_type=task_type,
            model=model,
            base_url=base_url,
            attempts=attempts,
            retries=max(0, attempts - 1),
            finish_reason=finish_reason,
            content_length=0,
            stream=stream,
            cancelled_due_to_deadline=cancelled_due_to_deadline,
            first_token_deadline_seconds=first_token_deadline_seconds,
            debug_label=debug_label,
        )
    )
    return ""
