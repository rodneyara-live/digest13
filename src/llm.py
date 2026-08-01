import os
import time
from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VOLUME_FALLBACK, REASONING_FALLBACK

MAX_RETRIES = 3
RETRY_BASE_DELAY = 30.0

_client = None
_token_usage: dict[str, dict] = {}


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


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 200,
             temperature: float = 0.3, model: str | None = None) -> str | None:
    if not GROQ_API_KEY:
        print("  No GROQ_API_KEY configured")
        return None

    primary = model or LLM_MODEL

    # Determine fallback: editorial callers use reasoning fallback, others use volume fallback
    if model and model == REASONING_FALLBACK:
        fallback = None  # no fallback for the fallback itself
    elif model:
        fallback = REASONING_FALLBACK
    else:
        fallback = VOLUME_FALLBACK

    result = _call_single_model(primary, system_prompt, user_prompt, max_tokens, temperature)

    if result == "TPD_EXHAUSTED" and fallback:
        print(f"  ⚠ {primary} agotado (TPD) → fallback a {fallback}")
        result = _call_single_model(fallback, system_prompt, user_prompt, max_tokens, temperature)
        if result == "TPD_EXHAUSTED":
            print(f"  ✖ {fallback} también agotado — sin respuesta")
            return None

    return result if result != "TPD_EXHAUSTED" else None
