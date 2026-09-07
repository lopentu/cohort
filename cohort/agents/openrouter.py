"""OpenRouter transport — replaces the Anthropic SDK entirely (docs/roadmap.md
"Scope revision", OpenRouter workstream).

Deliberately stdlib-only: `urllib.request` for the one HTTP call this needs,
not `httpx`. COHORT has zero HTTP dependencies today; adding a client library
to replace an SDK would be a lateral dependency swap, not the reduction it
looks like, and COHORT already hand-rolls narrow, well-understood surfaces
elsewhere (the FTS5 CJK-unigram trick, the write boundary itself instead of
an ORM) rather than reaching for a library. One endpoint with a well-defined
shape doesn't need one either.

OpenRouter's `/chat/completions` is OpenAI-compatible, not Anthropic-shaped.
epistemic-swarm's own OpenRouter transport doesn't do tool-calling at all
(it uses structured JSON output) — this wire format is designed fresh
against the OpenAI tool-calling spec, not ported from anywhere.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(Exception):
    """A transport-level failure — not a graph-rule violation, so this
    lives here rather than in `errors.py` (whose own docstring already
    draws that line)."""

    def __init__(self, message: str, *, status: int | None = None, cause: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.cause = cause  # "network" | "timeout" | "http_error" | "invalid_response" | "config"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")  # tolerate fields OpenRouter adds later


class OpenRouterFunctionCall(_Model):
    name: str
    arguments: str  # a JSON-encoded STRING, unlike Anthropic's already-parsed .input dict


class OpenRouterToolCall(_Model):
    id: str
    function: OpenRouterFunctionCall
    #: Replayed to the provider on the next turn. Some providers (Meta via
    #: OpenRouter, 2026-09-06) refuse a tool result whose originating call was
    #: echoed without its `type`, so it is kept and defaulted rather than
    #: dropped by the model_dump that builds the assistant turn.
    type: str = "function"


class OpenRouterMessage(_Model):
    role: str
    content: str | None = None
    tool_calls: list[OpenRouterToolCall] | None = None
    #: Reasoning models return their thinking as `reasoning_details`, and
    #: OpenRouter requires it to be sent back verbatim on the assistant turn
    #: that carried a tool call; without it the provider cannot match the tool
    #: result to the call ("No function call found for function call output",
    #: Meta, 2026-09-06) and the run dies on its second turn. Kept opaque:
    #: the content is the provider's, and it is only ever echoed.
    reasoning_details: list[dict] | None = None


class OpenRouterChoice(_Model):
    message: OpenRouterMessage
    finish_reason: str


class OpenRouterUsage(_Model):
    prompt_tokens: int
    completion_tokens: int
    #: OpenRouter reports this directly — no guessed pricing table needed.
    cost: float | None = None


class OpenRouterResponse(_Model):
    id: str
    model: str
    choices: list[OpenRouterChoice] = Field(min_length=1)
    usage: OpenRouterUsage


def default_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except HTTPError as e:
        return e.code, e.read()
    except URLError as e:
        cause = "timeout" if "timed out" in str(e.reason).lower() else "network"
        raise OpenRouterError(f"OpenRouter request failed: {e.reason}", cause=cause) from e


#: Ceiling on a single response's output tokens.
#:
#: Nothing bounded model output until 2026-09-02, which is a cost hole rather
#: than a correctness one: a reasoning model can spend far more than the task
#: needs, and the run's dollar cap would then be reached by fewer, longer
#: calls. The budget in `budget.py` is the hard stop; this keeps any one call
#: from consuming an unreasonable share of it.
#:
#: 2,800 is deliberately generous for this tool layer — the longest legitimate
#: response is a conjecture dossier, and those run a few hundred tokens. A
#: response that hits this ceiling is far more likely to be a model looping
#: than a task needing the room.
DEFAULT_MAX_OUTPUT_TOKENS = 2800

#: Reasoning models spend output tokens thinking before they write. Under the
#: 2,800 ceiling one such model (meta/muse-spark, 2026-09-06) spent every token
#: reasoning and returned nothing -- a truncated call that cost money and
#: produced no tool call. So the ceiling and the reasoning effort are both
#: settable from the environment: OPENROUTER_MAX_OUTPUT_TOKENS (0 or "none" =
#: no ceiling; the dollar budget in budget.py remains the hard stop) and
#: OPENROUTER_REASONING_EFFORT (low / medium / high, sent as OpenRouter's
#: `reasoning.effort`).
REASONING_EFFORTS = ("low", "medium", "high")


def output_limits_from_env() -> tuple[int | None, str | None]:
    """`(max_output_tokens, reasoning_effort)` as configured, with the module
    default for the ceiling when the variable is unset."""
    _load_dotenv()
    raw = (os.environ.get("OPENROUTER_MAX_OUTPUT_TOKENS") or "").strip().lower()
    if raw in ("", None):
        ceiling: int | None = DEFAULT_MAX_OUTPUT_TOKENS
    elif raw in ("0", "none", "off"):
        ceiling = None
    else:
        try:
            ceiling = int(raw)
        except ValueError as e:
            raise OpenRouterError(
                f"OPENROUTER_MAX_OUTPUT_TOKENS must be an integer, 0, or 'none'; got {raw!r}",
                cause="config",
            ) from e
    effort = (os.environ.get("OPENROUTER_REASONING_EFFORT") or "").strip().lower() or None
    if effort is not None and effort not in REASONING_EFFORTS:
        raise OpenRouterError(
            f"OPENROUTER_REASONING_EFFORT must be one of {REASONING_EFFORTS}; got {effort!r}",
            cause="config",
        )
    return ceiling, effort


def complete(
    model: str, messages: list[dict], tools: list[dict], *, api_key: str,
    timeout: float = 30.0, transport=default_transport,
    max_output_tokens: int | None = DEFAULT_MAX_OUTPUT_TOKENS,
    reasoning_effort: str | None = None,
) -> OpenRouterResponse:
    """Validated at the boundary before anything touches domain logic — the
    same discipline COHORT already applies to tool inputs, applied here to a
    network response. `transport` is the test seam: pass a fake callable in
    tests, no HTTP-mocking dependency needed.

    `max_output_tokens=None` sends no ceiling, which is what the provider
    defaults to; passing it explicitly is a decision, not an accident.
    `reasoning_effort` is forwarded as OpenRouter's `reasoning.effort` for
    models that think before they write."""
    payload: dict = {"model": model, "messages": messages, "tools": tools}
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens
    if reasoning_effort is not None:
        payload["reasoning"] = {"effort": reasoning_effort}
    body = json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    status, raw = transport(OPENROUTER_URL, headers, body, timeout)
    if status != 200:
        raise OpenRouterError(
            f"OpenRouter request failed (status {status}): {raw.decode('utf-8', errors='replace')}",
            status=status, cause="http_error",
        )
    try:
        return OpenRouterResponse.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as e:
        raise OpenRouterError("Invalid OpenRouter response", status=status, cause="invalid_response") from e


def _load_dotenv(path: Path = Path(".env")) -> None:
    """A small hand-rolled loader, not `python-dotenv`: COHORT's `.env` only
    ever needs flat `KEY=value` pairs, optionally wrapped in one matching
    pair of quotes (a common `.env` convention) — no multiline or `export`
    prefix support needed, so this is sufficient and honest about its
    limits, not a corner cut."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]  # a single matching pair of quotes, a common .env convention
        if key and key not in os.environ:
            os.environ[key] = value


def load_model_pool() -> list[str]:
    """The models a multi-agent run may draw on, from `OPENROUTER_MODELS`.

    Agents in one run must not share a model family
    (`cohort.agents.roster`), so a roster of several needs several models.
    `OPENROUTER_MODEL` is always included as the first entry — it is the
    default a single agent gets — and duplicates are dropped while keeping
    order, so the list reads as configured.

    An empty or unset pool is not an error: a one-agent run needs nothing more
    than the default model.
    """
    _load_dotenv()
    pool: list[str] = []
    default = os.environ.get("OPENROUTER_MODEL")
    if default:
        pool.append(default.strip())
    raw = os.environ.get("OPENROUTER_MODELS") or ""
    pool.extend(part.strip() for part in raw.split(",") if part.strip())
    return list(dict.fromkeys(pool))


def load_openrouter_config() -> tuple[str, str]:
    _load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    model = os.environ.get("OPENROUTER_MODEL")
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not set (see .env.example)", cause="config")
    if not model:
        raise OpenRouterError("OPENROUTER_MODEL is not set (see .env.example)", cause="config")
    return api_key, model
