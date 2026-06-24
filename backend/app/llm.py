from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .config import get_settings


def get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_chat_model,
        temperature=0,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def get_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.openai_embed_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
