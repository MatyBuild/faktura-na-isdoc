import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "claude").lower()
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")

# Fail fast: ověř, že je nastaven klíč pro zvolený provider
if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise RuntimeError("LLM_PROVIDER=openai, ale OPENAI_API_KEY není nastaven v .env")
if LLM_PROVIDER == "claude" and not ANTHROPIC_API_KEY:
    raise RuntimeError("LLM_PROVIDER=claude, ale ANTHROPIC_API_KEY není nastaven v .env")
