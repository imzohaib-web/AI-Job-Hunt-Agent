"""
core/llm_client.py — Groq primary, Gemini fallback. No retries on auth errors.
"""

import time
import logging
from typing import Optional, List

logger = logging.getLogger("job_agent.llm")


class LLMConfigurationError(Exception):
    """Raised when API keys are missing, wrong provider, or rejected (401)."""


def _is_auth_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    return (
        "authentication" in name
        or "401" in msg
        or "invalid api key" in msg
        or "invalid_api_key" in msg
        or "api key not valid" in msg
        or "permission" in msg
        and "denied" in msg
    )


def _is_rate_limit(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "rate_limit" in msg
        or "429" in msg
        or "rate limit" in msg
        or "resource_exhausted" in msg
        or "quota" in msg
    )


def _unwrap_retry_error(exc: BaseException) -> BaseException:
    """Extract the real exception from tenacity RetryError if present."""
    if type(exc).__name__ == "RetryError" and hasattr(exc, "last_attempt"):
        try:
            return exc.last_attempt.exception()
        except Exception:
            pass
    return exc


def validate_llm_config() -> Optional[str]:
    from core.config import GROQ_API_KEY, GOOGLE_API_KEY

    if GROQ_API_KEY:
        key = GROQ_API_KEY.strip()
        if key.startswith("xai-"):
            return (
                "GROQ_API_KEY looks like an xAI (Grok) key, not a Groq key. "
                "Use gsk_... from https://console.groq.com or set GEMINI_API_KEY."
            )
        if not key.startswith("gsk_"):
            return (
                "GROQ_API_KEY may be invalid — Groq keys usually start with gsk_."
            )
    if not GROQ_API_KEY and not GOOGLE_API_KEY:
        return (
            "No LLM API key found. Add GROQ_API_KEY (gsk_...) or "
            "GEMINI_API_KEY / GOOGLE_API_KEY to .env"
        )
    return None


def get_llm(provider: str = "groq", temperature: float = 0.3):
    from core.config import GROQ_API_KEY, GOOGLE_API_KEY, LLM_MODEL, GEMINI_MODEL

    provider = provider.lower()

    if provider == "groq":
        if not GROQ_API_KEY:
            return get_llm("gemini", temperature)
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=LLM_MODEL,
            api_key=GROQ_API_KEY,
            temperature=temperature,
            max_tokens=4096,
        )

    if provider == "gemini":
        if not GOOGLE_API_KEY:
            raise LLMConfigurationError(
                "Gemini key missing. Set GEMINI_API_KEY or GOOGLE_API_KEY in .env"
            )
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GOOGLE_API_KEY,
            temperature=temperature,
        )

    raise ValueError(f"Unknown provider: {provider}")


def _invoke_once(prompt: str, system: str, provider: str, temperature: float) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(provider, temperature)
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    response = llm.invoke(messages)
    content = response.content
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content).strip()


def _invoke_with_rate_limit_retries(
    prompt: str, system: str, provider: str, temperature: float, max_attempts: int = 3
) -> str:
    """Retry only on rate limits — never on authentication failures."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            return _invoke_once(prompt, system, provider, temperature)
        except Exception as e:
            last_exc = e
            if _is_auth_error(e):
                raise LLMConfigurationError(
                    f"{provider} authentication failed: {e}"
                ) from e
            if _is_rate_limit(e) and attempt < max_attempts - 1:
                logger.warning("Rate limited on %s, waiting 30s…", provider)
                time.sleep(30)
                continue
            raise
    raise last_exc  # type: ignore[misc]


def _provider_chain(explicit: Optional[str] = None) -> List[str]:
    """Build ordered list of providers to try."""
    from core.config import GROQ_API_KEY, GOOGLE_API_KEY, LLM_PROVIDER

    if explicit and explicit.lower() in ("groq", "gemini"):
        chain = [explicit.lower()]
    elif LLM_PROVIDER in ("groq", "gemini"):
        chain = [LLM_PROVIDER]
    else:
        chain = []
        if GROQ_API_KEY:
            chain.append("groq")
        if GOOGLE_API_KEY:
            chain.append("gemini")

    # Deduplicate
    seen = set()
    out = []
    for p in chain:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def call_llm(
    prompt: str,
    system: str = "",
    provider: Optional[str] = None,
    temperature: float = 0.3,
) -> str:
    from core.config import GOOGLE_API_KEY

    warn = validate_llm_config()
    if warn and not GOOGLE_API_KEY:
        raise LLMConfigurationError(warn)

    chain = _provider_chain(provider)
    if not chain:
        raise LLMConfigurationError(
            validate_llm_config()
            or "Set GROQ_API_KEY or GEMINI_API_KEY in .env"
        )

    last_auth: Optional[Exception] = None
    for prov in chain:
        try:
            logger.info("LLM call using provider: %s", prov)
            return _invoke_with_rate_limit_retries(prompt, system, prov, temperature)
        except LLMConfigurationError as e:
            last_auth = e
            logger.warning("%s failed, trying next provider…", prov)
            continue
        except Exception as e:
            if _is_rate_limit(e) and prov == "gemini":
                raise LLMConfigurationError(_friendly_error(e)) from e
            raise

    if last_auth:
        raise LLMConfigurationError(
            "All LLM providers failed. "
            "Groq: verify GROQ_API_KEY at https://console.groq.com (starts with gsk_). "
            "Gemini: check GEMINI_API_KEY / quota at https://aistudio.google.com/apikey. "
            f"Last error: {last_auth}"
        ) from last_auth
    raise LLMConfigurationError("LLM call failed for unknown reasons.")


def _friendly_error(exc: Exception) -> str:
    """Map provider errors to actionable messages."""
    msg = str(exc).lower()
    if "401" in msg or "invalid api key" in msg:
        return (
            "Groq API key rejected (401). Create a new key at https://console.groq.com "
            "and set GROQ_API_KEY=gsk_... in .env"
        )
    if "429" in msg or "quota" in msg or "resource_exhausted" in msg:
        return (
            "Gemini quota exceeded (429). Wait and retry, or set GEMINI_MODEL=gemini-1.5-flash "
            "in .env, or fix your Groq key so the app uses Groq instead."
        )
    return str(exc)


def call_llm_json(prompt: str, system: str = "", provider: Optional[str] = None) -> dict:
    import json
    import re

    system_with_json = (
        system + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
        "No explanation, no markdown, no code fences."
    ).strip()

    try:
        raw = call_llm(
            prompt, system=system_with_json, provider=provider, temperature=0.1
        )
    except LLMConfigurationError:
        raise
    except Exception as e:
        inner = _unwrap_retry_error(e)
        if _is_auth_error(inner):
            raise LLMConfigurationError(str(inner)) from inner
        logger.error("LLM JSON call failed: %s", inner)
        return {"error": str(inner), "raw": ""}

    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: %s\nRaw: %s", e, raw[:300])
        return {"error": str(e), "raw": raw}
