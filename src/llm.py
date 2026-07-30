import os
import google.generativeai as genai
from groq import Groq
from config import GROQ_API_KEY, GEMINI_API_KEY, LLM_MODEL


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 200, temperature: float = 0.3) -> str | None:
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(
                LLM_MODEL,
                system_instruction=system_prompt,
            )
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            return response.text.strip()
        except Exception as e:
            print(f"  Gemini error: {e}")
            return None

    if GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"  Groq error: {e}")
            return None

    print("  No API key configured (GROQ_API_KEY or GEMINI_API_KEY)")
    return None
