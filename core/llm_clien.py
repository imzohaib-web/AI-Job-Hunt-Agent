"""
core/llm_client.py
==================
LLM wrapper that uses Groq (free, fast) as primary and
Google Gemini (free tier) as fallback. No OpenAI needed.

Free quotas:
  Groq  — 6,000 req/day, ~600k tokens/min (LLaMA 3.1 70B)
  Gemini — 15 req/min, 1M tokens/day (gemini-1.5-flash)
"""

import time
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("job_agent.llm")


def get_llm(provider: str = "groq", temperature: float = 0.3):
    """
    Return a LangChain-compatible chat model.

    Args:
        provider: "groq" (default) or "gemini"
        temperature: 0.0–1.0, lower = more deterministic

    Returns:
        ChatGroq or ChatGoogleGenerativeAI instance
    """
    from core.config import GROQ_API_KEY, GOOGLE_API_KEY, LLM_MODEL

    if provider == "groq":
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY missing, falling back to Gemini")
            return get_llm("gemini", temperature)
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=LLM_MODEL,
                api_key=GROQ_API_KEY,
                temperature=temperature,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error("Groq init failed: %s. Falling back to Gemini.", e)
            return get_llm("gemini", temperature)

    elif provider == "gemini":
        if not GOOGLE_API_KEY:
            raise ValueError("No LLM API key configured. Add GROQ_API_KEY or GOOGLE_API_KEY to .env")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",   # free tier model
            google_api_key=GOOGLE_API_KEY,
            temperature=temperature,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def call_llm(prompt: str, system: str = "", provider: str = "groq",
             temperature: float = 0.3) -> str:
    """
    Call the LLM with automatic retry on rate limits.

    Args:
        prompt:      User message
        system:      System prompt (optional)
        provider:    "groq" or "gemini"
        temperature: Creativity level

    Returns:
        Response text as string
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(provider, temperature)
    messages = []

    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))

    try:
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        if "rate_limit" in str(e).lower() or "429" in str(e):
            logger.warning("Rate limited. Waiting 30s before retry...")
            time.sleep(30)
            raise   # tenacity will retry
        logger.error("LLM call failed: %s", e)
        raise


def call_llm_json(prompt: str, system: str = "", provider: str = "groq") -> dict:
    """
    Call LLM and parse response as JSON.
    Strips markdown code fences if present.

    Returns:
        Parsed dict/list, or {"error": ..., "raw": ...} on failure
    """
    import json
    import re

    system_with_json = (system + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
                        "No explanation, no markdown, no code fences.").strip()

    raw = call_llm(prompt, system=system_with_json, provider=provider, temperature=0.1)

    # Strip markdown code fences if model added them anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: %s\nRaw: %s", e, raw[:300])
        return {"error": str(e), "raw": raw}