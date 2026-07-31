import os
import time
from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL

MAX_RETRIES = 3
RETRY_BASE_DELAY = 30.0


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 200,
             temperature: float = 0.3, model: str | None = None) -> str | None:
    if not GROQ_API_KEY:
        print("  No GROQ_API_KEY configured")
        return None

    client = Groq(api_key=GROQ_API_KEY)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model or LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            error = str(e)
            is_rate_limit = "429" in error or "rate_limit" in error.lower()
            is_tpd_exhausted = "tokens per day" in error.lower()
            if is_rate_limit and not is_tpd_exhausted and attempt < MAX_RETRIES:
                print(f"  [rate limit, reintento {attempt}/{MAX_RETRIES} en {int(RETRY_BASE_DELAY * attempt)}s]")
                time.sleep(RETRY_BASE_DELAY * attempt)
                continue
            print(f"  Groq error: {e}")
            return None

    return None
