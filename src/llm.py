import os
import time
from groq import Groq
from config import (
    GROQ_API_KEY,
    LLM_MODEL,
    FILTER_MODEL,
    EDITORIAL_MODEL,
    VOLUME_FALLBACK,
    REASONING_FALLBACK,
)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 30.0

_client = None
_token_usage: dict[str, dict] = {}

# Models whose daily quota (TPD) is already known to be spent in this run. Once a
# model lands here every later call skips it and goes straight down the chain,
# instead of burning a round-trip per call to rediscover it's dead.
_exhausted: set[str] = set()


def _build_fallback_chain() -> dict[str, str]:
    """Map each primary model to its backup. Explicit, rather than inferred from
    the shape of `call_llm`'s `model` argument — with three primaries there's no
    longer a reliable way to guess which quota a caller belongs to."""
    chain = {
        # The filter model falls *up* to the paragraph model rather than dead-ending:
        # with no model for stage 1 nothing gets approved and the run aborts, so
        # spending paragraph headroom beats producing no digest. It defaults to the
        # volume fallback itself, so this is the only way it gets a backup at all.
        # 8b → 70b → 8b is a cycle; _first_available's `seen` guard terminates it.
        FILTER_MODEL: LLM_MODEL,
        LLM_MODEL: VOLUME_FALLBACK,
        EDITORIAL_MODEL: REASONING_FALLBACK,
    }
    # A model is never its own fallback: FILTER_MODEL defaults to VOLUME_FALLBACK
    # itself, and .env can point any primary straight at its backup.
    return {primary: backup for primary, backup in chain.items() if primary != backup}


FALLBACK_CHAIN = _build_fallback_chain()


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def get_token_usage() -> dict[str, dict]:
    return _token_usage.copy()


def _track_usage(model_name: str, usage) -> None:
    if model_name not in _token_usage:
        _token_usage[model_name] = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
    _token_usage[model_name]["prompt"] += usage.prompt_tokens
    _token_usage[model_name]["completion"] += usage.completion_tokens
    _token_usage[model_name]["total"] += usage.total_tokens
    _token_usage[model_name]["calls"] += 1


def _call_single_model(model: str, system_prompt: str, user_prompt: str,
                       max_tokens: int, temperature: float) -> str | None:
    client = _get_client()
    # Reasoning models (gpt-oss-*) include thinking by default — disable it
    is_reasoning = model and ("gpt-oss" in model or "qwen" in model)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            kwargs = dict(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if is_reasoning:
                kwargs["include_reasoning"] = False
            response = client.chat.completions.create(**kwargs)
            finish = response.choices[0].finish_reason
            if finish == "length":
                print(f"  ⚠ TRUNCADO: finish_reason=length (max_tokens={max_tokens})")
            _track_usage(model, response.usage)
            return response.choices[0].message.content.strip()
        except Exception as e:
            error = str(e)
            is_tpd = "tokens per day" in error.lower()
            if is_tpd:
                return "TPD_EXHAUSTED"
            is_rate_limit = "429" in error or "rate_limit" in error.lower()
            if is_rate_limit and attempt < MAX_RETRIES:
                print(f"  [rate limit, reintento {attempt}/{MAX_RETRIES} en {int(RETRY_BASE_DELAY * attempt)}s]")
                time.sleep(RETRY_BASE_DELAY * attempt)
                continue
            print(f"  Groq error: {e}")
            return None
    return None


def _mark_exhausted(model: str) -> None:
    """Record a spent quota and announce the switch once, not once per call."""
    if model in _exhausted:
        return
    _exhausted.add(model)
    backup = FALLBACK_CHAIN.get(model)
    if backup:
        print(f"  ⚠ {model} agotado (TPD) → el resto de la corrida usa {backup}")
    else:
        print(f"  ✖ {model} agotado (TPD) y sin respaldo")


def _first_available(primary: str) -> str | None:
    """Walk the fallback chain past every model already out of quota."""
    model = primary
    seen: set[str] = set()
    while model in _exhausted:
        seen.add(model)
        model = FALLBACK_CHAIN.get(model)
        if model is None or model in seen:
            return None
    return model


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 200,
             temperature: float = 0.3, model: str | None = None) -> str | None:
    if not GROQ_API_KEY:
        print("  No GROQ_API_KEY configured")
        return None

    current = _first_available(model or LLM_MODEL)

    while current is not None:
        result = _call_single_model(current, system_prompt, user_prompt, max_tokens, temperature)
        if result != "TPD_EXHAUSTED":
            return result
        _mark_exhausted(current)
        current = _first_available(current)

    return None
