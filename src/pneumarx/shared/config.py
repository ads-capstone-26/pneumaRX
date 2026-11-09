"""Only settings needed by the modular MIMIC workflow."""
import os
from pathlib import Path

from dotenv import load_dotenv

from .paths import PROJECT_ROOT


class Config:
    def __init__(self, env_path: str | Path | None = None, model: str | None = None):
        load_dotenv(env_path or PROJECT_ROOT / '.env', override=False)
        self.LLM_PATH = model or os.getenv('FIGURE3_LLM_MODEL') or os.getenv('LLM_PATH', '')
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
        self.AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY', '')
        self.AZURE_OPENAI_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT', '')
        self.AZURE_API_VERSION = os.getenv('AZURE_API_VERSION', '2024-12-01-preview')
        self.USE_AZURE_LLM = os.getenv('USE_AZURE_LLM', 'true').lower() == 'true'
        # Persistent memory is deliberately outside the current component contract.
        self.ENABLE_MEMORY_LAYER = False
        self.MEMORY_RETRIEVAL_TOP_K = 0
