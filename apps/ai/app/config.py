import os


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
        self.gemini_model = (os.environ.get("GEMINI_MODEL") or "gemini-2.0-flash").strip()

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


settings = Settings()
