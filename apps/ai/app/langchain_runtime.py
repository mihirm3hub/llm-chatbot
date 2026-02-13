import json
import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from .config import settings


def llm_enabled() -> bool:
    if settings.llm_provider == "gemini":
        return bool(settings.gemini_api_key)
    if settings.llm_provider == "kimi":
        return bool(settings.moonshot_api_key)
    return bool(settings.openai_api_key)


def get_chat_model(*, temperature: float = 0) -> BaseChatModel:
    provider = settings.llm_provider

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=max(0, float(temperature)),
            max_retries=1,
            timeout=8,
        )

    # OpenAI-compatible (OpenAI or Kimi/Moonshot)
    from langchain_openai import ChatOpenAI  # type: ignore

    if provider == "kimi":
        api_key = settings.moonshot_api_key
        model = settings.kimi_model
        base_url = settings.kimi_base_url
        # LangChain+OpenAI SDK supports base_url param in recent versions.
        # If an older version is in play, set the client-level base via legacy param or env.
        try:
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=max(0, float(temperature)),
            )
        except TypeError:
            try:
                return ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    openai_api_base=base_url,
                    temperature=max(0, float(temperature)),
                )
            except TypeError:
                os.environ["OPENAI_API_BASE"] = base_url
                return ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    temperature=max(0, float(temperature)),
                )

    if provider != "openai":
        raise ValueError(f"Unsupported llm_provider={settings.llm_provider}")

    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=max(0, float(temperature)),
    )


def safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)
