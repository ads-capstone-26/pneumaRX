"""Lazy provider creation: offline components do not import the OpenAI SDK."""
from dataclasses import replace
import logging

from .config import Config


class LanguageModelAPI:
    def __init__(self, llm):
        self.llm = llm

    def chat(self, messages, option):
        return self.llm.chat(messages, replace(option, max_new_tokens=8000, stream=False))


def configured_llm(config: Config):
    if not config.LLM_PATH:
        raise ValueError('Set LLM_PATH in .env or pass --model for live runs.')
    if config.USE_AZURE_LLM:
        if not config.AZURE_OPENAI_API_KEY or not config.AZURE_OPENAI_ENDPOINT:
            raise ValueError('Azure API key and endpoint are required.')
        from .azure_openai_llm import AzureOpenAILLM as Adapter
    else:
        if not config.OPENAI_API_KEY:
            raise ValueError('OPENAI_API_KEY is required.')
        from .openai_llm import OpenAILLM as Adapter
    llm = Adapter(config, logging.getLogger('pneumarx.llm'))
    llm.client = llm.client.with_options(timeout=90, max_retries=0)
    return llm
