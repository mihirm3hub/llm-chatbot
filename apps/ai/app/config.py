import os
import logging


logger = logging.getLogger("ai")


def _norm_provider(value: str | None) -> str:
    p = (value or "").strip().lower()
    if p in {"moonshot", "kimi"}:
        return "kimi"
    if p in {"openai"}:
        return "openai"
    if p in {"gemini"}:
        return "gemini"
    return "openai"


class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL")

        # If true, fail the request when session persistence fails.
        self.require_session_persistence = (
            (os.environ.get("REQUIRE_SESSION_PERSISTENCE") or "").strip().lower() in {"1", "true", "yes"}
        )

        # Preferred provider (may be auto-fallback if its key is missing).
        self.llm_provider = _norm_provider(os.environ.get("LLM_PROVIDER") or "gemini")

        # OpenAI (optional)
        self.openai_api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        self.openai_model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()

        # Kimi / Moonshot (OpenAI-compatible)
        self.moonshot_api_key = (os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY") or "").strip()
        self.kimi_model = (os.environ.get("KIMI_MODEL") or "kimi-k2-turbo-preview").strip()
        self.kimi_base_url = (os.environ.get("KIMI_BASE_URL") or "https://api.moonshot.ai/v1").strip()

        # Gemini
        self.gemini_api_key = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        ).strip()
        self.gemini_model = (os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash-lite").strip()

        # Auto-fallback: if the preferred provider has no key configured,
        # pick the first available provider so the LLM can still respond.
        available = []
        if self.gemini_api_key:
            available.append("gemini")
        if self.moonshot_api_key:
            available.append("kimi")
        if self.openai_api_key:
            available.append("openai")

        if self.llm_provider == "gemini" and not self.gemini_api_key and available:
            self.llm_provider = available[0]
        elif self.llm_provider == "kimi" and not self.moonshot_api_key and available:
            self.llm_provider = available[0]
        elif self.llm_provider == "openai" and not self.openai_api_key and available:
            self.llm_provider = available[0]

        # If the preferred provider has no credentials and there is no fallback,
        # fail fast with a clear message instead of silently keeping an unusable provider.
        if not available:
            missing = []
            if not self.gemini_api_key:
                missing.append("GEMINI_API_KEY")
            if not self.moonshot_api_key:
                missing.append("MOONSHOT_API_KEY/KIMI_API_KEY")
            if not self.openai_api_key:
                missing.append("OPENAI_API_KEY")
            logger.warning(
                "No LLM provider credentials configured; llm_provider=%s missing=%s",
                self.llm_provider,
                ",".join(missing),
            )
            raise RuntimeError(
                "No LLM provider credentials configured. Set one of GEMINI_API_KEY, MOONSHOT_API_KEY/KIMI_API_KEY, OPENAI_API_KEY."
            )


settings = Settings()
