import json
import logging
import mimetypes
import os
import shutil

import uuid, statistics
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Union, Dict, Any

from pydantic import BaseModel, Field

from collections import defaultdict
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import List, Dict, Any, Tuple, Set

import re

import asyncio
import inspect

from open_webui.retrieval.web import (
    bing, bocha, brave, duckduckgo, exa, google_pse, jina_search, kagi,
    mojeek, perplexity, searchapi, serpapi, searxng, serper, serply,
    serpstack, tavily, sougou
)

from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from open_webui.retrieval.web.utils import get_web_loader, _crawl4ai_fetch_docs

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    Request,
    status,
    APIRouter,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
import tiktoken

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)
from langchain_core.documents import Document

from open_webui.models.files import FileModel, Files
from open_webui.models.knowledge import Knowledges
from open_webui.storage.provider import Storage

from open_webui.retrieval.vector.connector import VECTOR_DB_CLIENT

# Document loaders
from open_webui.retrieval.loaders.main import Loader
from open_webui.retrieval.loaders.youtube import YoutubeLoader

from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_verified_user
from open_webui.utils.misc import calculate_sha256_string
from open_webui.config import (
    DEFAULT_LOCALE,
    RAG_EMBEDDING_CONTENT_PREFIX,
    RAG_EMBEDDING_QUERY_PREFIX,
)

from open_webui.retrieval.web.main import SearchResult

from open_webui.retrieval.utils import (
    get_embedding_function,
    get_model_path,
    query_collection,
    query_collection_with_hybrid_search,
    query_doc,
    query_doc_with_hybrid_search,
)
from open_webui.utils.misc import (
    calculate_sha256_string,
)
from open_webui.utils.auth import get_admin_user, get_verified_user

from open_webui.config import (
    ENV,
    RAG_EMBEDDING_MODEL_AUTO_UPDATE,
    RAG_EMBEDDING_MODEL_TRUST_REMOTE_CODE,
    RAG_RERANKING_MODEL_AUTO_UPDATE,
    RAG_RERANKING_MODEL_TRUST_REMOTE_CODE,
    UPLOAD_DIR,
    DEFAULT_LOCALE,
    RAG_EMBEDDING_CONTENT_PREFIX,
    RAG_EMBEDDING_QUERY_PREFIX,
)
from open_webui.env import (
    SRC_LOG_LEVELS,
    DEVICE_TYPE,
    DOCKER,
)

ENGINES = {
    "bing": bing,
    "bocha": bocha,
    "brave": brave,
    "duckduckgo": duckduckgo,
    "exa": exa,
    "google_pse": google_pse,
    "jina": jina_search,
    "kagi": kagi,
    "mojeek": mojeek,
    "perplexity": perplexity,
    "searchapi": searchapi,
    "serpapi": serpapi,
    "searxng": searxng,
    "serper": serper,
    "serply": serply,
    "serpstack": serpstack,
    "tavily": tavily,
    "sougou": sougou,
}

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])


##########################################
#
# Utility functions
#
##########################################


def get_ef(
    engine: str,
    embedding_model: str,
    auto_update: bool = False,
):
    ef = None
    if embedding_model and engine == "":
        from sentence_transformers import SentenceTransformer

        try:
            ef = SentenceTransformer(
                get_model_path(embedding_model, auto_update),
                device=DEVICE_TYPE,
                trust_remote_code=RAG_EMBEDDING_MODEL_TRUST_REMOTE_CODE,
            )
        except Exception as e:
            log.debug(f"Error loading SentenceTransformer: {e}")

    return ef


def get_rf(
    reranking_model: Optional[str] = None,
    auto_update: bool = False,
):
    rf = None
    if reranking_model:
        if any(model in reranking_model for model in ["jinaai/jina-colbert-v2"]):
            try:
                from open_webui.retrieval.models.colbert import ColBERT

                rf = ColBERT(
                    get_model_path(reranking_model, auto_update),
                    env="docker" if DOCKER else None,
                )

            except Exception as e:
                log.error(f"ColBERT: {e}")
                raise Exception(ERROR_MESSAGES.DEFAULT(e))
        else:
            import sentence_transformers

            try:
                rf = sentence_transformers.CrossEncoder(
                    get_model_path(reranking_model, auto_update),
                    device=DEVICE_TYPE,
                    trust_remote_code=RAG_RERANKING_MODEL_TRUST_REMOTE_CODE,
                )
            except Exception as e:
                log.error(f"CrossEncoder: {e}")
                raise Exception(ERROR_MESSAGES.DEFAULT("CrossEncoder error"))
    return rf


##########################################
#
# API routes
#
##########################################


router = APIRouter()


class CollectionNameForm(BaseModel):
    collection_name: Optional[str] = None

class ProcessUrlForm(BaseModel):
    url: str
    collection_name: Optional[str] = None

class SearchForm(BaseModel):
    query: str
    collection_name: Optional[str] = ""
    limit: Optional[int] = Field(default=None, ge=1, le=100)
    page_size: Optional[int] = Field(default=None, ge=1, le=10)
    concurrency: Optional[int] = Field(default=None, ge=1, le=10)

@router.get("/")
async def get_status(request: Request):
    return {
        "status": True,
        "chunk_size": request.app.state.config.CHUNK_SIZE,
        "chunk_overlap": request.app.state.config.CHUNK_OVERLAP,
        "template": request.app.state.config.RAG_TEMPLATE,
        "embedding_engine": request.app.state.config.RAG_EMBEDDING_ENGINE,
        "embedding_model": request.app.state.config.RAG_EMBEDDING_MODEL,
        "reranking_model": request.app.state.config.RAG_RERANKING_MODEL,
        "embedding_batch_size": request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
    }


@router.get("/embedding")
async def get_embedding_config(request: Request, user=Depends(get_admin_user)):
    return {
        "status": True,
        "embedding_engine": request.app.state.config.RAG_EMBEDDING_ENGINE,
        "embedding_model": request.app.state.config.RAG_EMBEDDING_MODEL,
        "embedding_batch_size": request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
        "openai_config": {
            "url": request.app.state.config.RAG_OPENAI_API_BASE_URL,
            "key": request.app.state.config.RAG_OPENAI_API_KEY,
        },
        "ollama_config": {
            "url": request.app.state.config.RAG_OLLAMA_BASE_URL,
            "key": request.app.state.config.RAG_OLLAMA_API_KEY,
        },
    }


@router.get("/reranking")
async def get_reraanking_config(request: Request, user=Depends(get_admin_user)):
    return {
        "status": True,
        "reranking_model": request.app.state.config.RAG_RERANKING_MODEL,
    }


class OpenAIConfigForm(BaseModel):
    url: str
    key: str


class OllamaConfigForm(BaseModel):
    url: str
    key: str


class EmbeddingModelUpdateForm(BaseModel):
    openai_config: Optional[OpenAIConfigForm] = None
    ollama_config: Optional[OllamaConfigForm] = None
    embedding_engine: str
    embedding_model: str
    embedding_batch_size: Optional[int] = 1


@router.post("/embedding/update")
async def update_embedding_config(
    request: Request, form_data: EmbeddingModelUpdateForm, user=Depends(get_admin_user)
):
    log.info(
        f"Updating embedding model: {request.app.state.config.RAG_EMBEDDING_MODEL} to {form_data.embedding_model}"
    )
    try:
        request.app.state.config.RAG_EMBEDDING_ENGINE = form_data.embedding_engine
        request.app.state.config.RAG_EMBEDDING_MODEL = form_data.embedding_model

        if request.app.state.config.RAG_EMBEDDING_ENGINE in ["ollama", "openai"]:
            if form_data.openai_config is not None:
                request.app.state.config.RAG_OPENAI_API_BASE_URL = (
                    form_data.openai_config.url
                )
                request.app.state.config.RAG_OPENAI_API_KEY = (
                    form_data.openai_config.key
                )

            if form_data.ollama_config is not None:
                request.app.state.config.RAG_OLLAMA_BASE_URL = (
                    form_data.ollama_config.url
                )
                request.app.state.config.RAG_OLLAMA_API_KEY = (
                    form_data.ollama_config.key
                )

            request.app.state.config.RAG_EMBEDDING_BATCH_SIZE = (
                form_data.embedding_batch_size
            )

        request.app.state.ef = get_ef(
            request.app.state.config.RAG_EMBEDDING_ENGINE,
            request.app.state.config.RAG_EMBEDDING_MODEL,
        )

        request.app.state.EMBEDDING_FUNCTION = get_embedding_function(
            request.app.state.config.RAG_EMBEDDING_ENGINE,
            request.app.state.config.RAG_EMBEDDING_MODEL,
            request.app.state.ef,
            (
                request.app.state.config.RAG_OPENAI_API_BASE_URL
                if request.app.state.config.RAG_EMBEDDING_ENGINE == "openai"
                else request.app.state.config.RAG_OLLAMA_BASE_URL
            ),
            (
                request.app.state.config.RAG_OPENAI_API_KEY
                if request.app.state.config.RAG_EMBEDDING_ENGINE == "openai"
                else request.app.state.config.RAG_OLLAMA_API_KEY
            ),
            request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
        )

        return {
            "status": True,
            "embedding_engine": request.app.state.config.RAG_EMBEDDING_ENGINE,
            "embedding_model": request.app.state.config.RAG_EMBEDDING_MODEL,
            "embedding_batch_size": request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
            "openai_config": {
                "url": request.app.state.config.RAG_OPENAI_API_BASE_URL,
                "key": request.app.state.config.RAG_OPENAI_API_KEY,
            },
            "ollama_config": {
                "url": request.app.state.config.RAG_OLLAMA_BASE_URL,
                "key": request.app.state.config.RAG_OLLAMA_API_KEY,
            },
        }
    except Exception as e:
        log.exception(f"Problem updating embedding model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


class RerankingModelUpdateForm(BaseModel):
    reranking_model: str


@router.post("/reranking/update")
async def update_reranking_config(
    request: Request, form_data: RerankingModelUpdateForm, user=Depends(get_admin_user)
):
    log.info(
        f"Updating reranking model: {request.app.state.config.RAG_RERANKING_MODEL} to {form_data.reranking_model}"
    )
    try:
        request.app.state.config.RAG_RERANKING_MODEL = form_data.reranking_model

        try:
            request.app.state.rf = get_rf(
                request.app.state.config.RAG_RERANKING_MODEL,
                True,
            )
        except Exception as e:
            log.error(f"Error loading reranking model: {e}")
            request.app.state.config.ENABLE_RAG_HYBRID_SEARCH = False

        return {
            "status": True,
            "reranking_model": request.app.state.config.RAG_RERANKING_MODEL,
        }
    except Exception as e:
        log.exception(f"Problem updating reranking model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


@router.get("/config")
async def get_rag_config(request: Request, user=Depends(get_admin_user)):
    return {
        "status": True,
        # RAG settings
        "RAG_TEMPLATE": request.app.state.config.RAG_TEMPLATE,
        "TOP_K": request.app.state.config.TOP_K,
        "BYPASS_EMBEDDING_AND_RETRIEVAL": request.app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL,
        "RAG_FULL_CONTEXT": request.app.state.config.RAG_FULL_CONTEXT,
        # Hybrid search settings
        "ENABLE_RAG_HYBRID_SEARCH": request.app.state.config.ENABLE_RAG_HYBRID_SEARCH,
        "TOP_K_RERANKER": request.app.state.config.TOP_K_RERANKER,
        "RELEVANCE_THRESHOLD": request.app.state.config.RELEVANCE_THRESHOLD,
        # Content extraction settings
        "CONTENT_EXTRACTION_ENGINE": request.app.state.config.CONTENT_EXTRACTION_ENGINE,
        "PDF_EXTRACT_IMAGES": request.app.state.config.PDF_EXTRACT_IMAGES,
        "TIKA_SERVER_URL": request.app.state.config.TIKA_SERVER_URL,
        "DOCLING_SERVER_URL": request.app.state.config.DOCLING_SERVER_URL,
        "DOCUMENT_INTELLIGENCE_ENDPOINT": request.app.state.config.DOCUMENT_INTELLIGENCE_ENDPOINT,
        "DOCUMENT_INTELLIGENCE_KEY": request.app.state.config.DOCUMENT_INTELLIGENCE_KEY,
        "MISTRAL_OCR_API_KEY": request.app.state.config.MISTRAL_OCR_API_KEY,
        # Chunking settings
        "TEXT_SPLITTER": request.app.state.config.TEXT_SPLITTER,
        "CHUNK_SIZE": request.app.state.config.CHUNK_SIZE,
        "CHUNK_OVERLAP": request.app.state.config.CHUNK_OVERLAP,
        # File upload settings
        "FILE_MAX_SIZE": request.app.state.config.FILE_MAX_SIZE,
        "FILE_MAX_COUNT": request.app.state.config.FILE_MAX_COUNT,
        # Integration settings
        "ENABLE_GOOGLE_DRIVE_INTEGRATION": request.app.state.config.ENABLE_GOOGLE_DRIVE_INTEGRATION,
        "ENABLE_ONEDRIVE_INTEGRATION": request.app.state.config.ENABLE_ONEDRIVE_INTEGRATION,
        # Web search settings
        "web": {
            "ENABLE_WEB_SEARCH": request.app.state.config.ENABLE_WEB_SEARCH,
            "WEB_SEARCH_ENGINE": request.app.state.config.WEB_SEARCH_ENGINE,
            "WEB_SEARCH_TRUST_ENV": request.app.state.config.WEB_SEARCH_TRUST_ENV,
            "WEB_SEARCH_RESULT_COUNT": request.app.state.config.WEB_SEARCH_RESULT_COUNT,
            "WEB_SEARCH_CONCURRENT_REQUESTS": request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS,
            "WEB_SEARCH_DOMAIN_FILTER_LIST": request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST,
            "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL": request.app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL,
            "SEARXNG_QUERY_URL": request.app.state.config.SEARXNG_QUERY_URL,
            "GOOGLE_PSE_API_KEY": request.app.state.config.GOOGLE_PSE_API_KEY,
            "GOOGLE_PSE_ENGINE_ID": request.app.state.config.GOOGLE_PSE_ENGINE_ID,
            "BRAVE_SEARCH_API_KEY": request.app.state.config.BRAVE_SEARCH_API_KEY,
            "KAGI_SEARCH_API_KEY": request.app.state.config.KAGI_SEARCH_API_KEY,
            "MOJEEK_SEARCH_API_KEY": request.app.state.config.MOJEEK_SEARCH_API_KEY,
            "BOCHA_SEARCH_API_KEY": request.app.state.config.BOCHA_SEARCH_API_KEY,
            "SERPSTACK_API_KEY": request.app.state.config.SERPSTACK_API_KEY,
            "SERPSTACK_HTTPS": request.app.state.config.SERPSTACK_HTTPS,
            "SERPER_API_KEY": request.app.state.config.SERPER_API_KEY,
            "SERPLY_API_KEY": request.app.state.config.SERPLY_API_KEY,
            "TAVILY_API_KEY": request.app.state.config.TAVILY_API_KEY,
            "SEARCHAPI_API_KEY": request.app.state.config.SEARCHAPI_API_KEY,
            "SEARCHAPI_ENGINE": request.app.state.config.SEARCHAPI_ENGINE,
            "SERPAPI_API_KEY": request.app.state.config.SERPAPI_API_KEY,
            "SERPAPI_ENGINE": request.app.state.config.SERPAPI_ENGINE,
            "JINA_API_KEY": request.app.state.config.JINA_API_KEY,
            "BING_SEARCH_V7_ENDPOINT": request.app.state.config.BING_SEARCH_V7_ENDPOINT,
            "BING_SEARCH_V7_SUBSCRIPTION_KEY": request.app.state.config.BING_SEARCH_V7_SUBSCRIPTION_KEY,
            "EXA_API_KEY": request.app.state.config.EXA_API_KEY,
            "PERPLEXITY_API_KEY": request.app.state.config.PERPLEXITY_API_KEY,
            "SOUGOU_API_SID": request.app.state.config.SOUGOU_API_SID,
            "SOUGOU_API_SK": request.app.state.config.SOUGOU_API_SK,
            "WEB_LOADER_ENGINE": request.app.state.config.WEB_LOADER_ENGINE,
            "ENABLE_WEB_LOADER_SSL_VERIFICATION": request.app.state.config.ENABLE_WEB_LOADER_SSL_VERIFICATION,
            "PLAYWRIGHT_WS_URL": request.app.state.config.PLAYWRIGHT_WS_URL,
            "PLAYWRIGHT_TIMEOUT": request.app.state.config.PLAYWRIGHT_TIMEOUT,
            "FIRECRAWL_API_KEY": request.app.state.config.FIRECRAWL_API_KEY,
            "FIRECRAWL_API_BASE_URL": request.app.state.config.FIRECRAWL_API_BASE_URL,
            "TAVILY_EXTRACT_DEPTH": request.app.state.config.TAVILY_EXTRACT_DEPTH,
            "YOUTUBE_LOADER_LANGUAGE": request.app.state.config.YOUTUBE_LOADER_LANGUAGE,
            "YOUTUBE_LOADER_PROXY_URL": request.app.state.config.YOUTUBE_LOADER_PROXY_URL,
            "YOUTUBE_LOADER_TRANSLATION": request.app.state.YOUTUBE_LOADER_TRANSLATION,
        },
    }


class WebConfig(BaseModel):
    ENABLE_WEB_SEARCH: Optional[bool] = None
    WEB_SEARCH_ENGINE: Optional[str] = None
    WEB_SEARCH_TRUST_ENV: Optional[bool] = None
    WEB_SEARCH_RESULT_COUNT: Optional[int] = None
    WEB_SEARCH_CONCURRENT_REQUESTS: Optional[int] = None
    WEB_SEARCH_DOMAIN_FILTER_LIST: Optional[List[str]] = []
    BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL: Optional[bool] = None
    SEARXNG_QUERY_URL: Optional[str] = None
    GOOGLE_PSE_API_KEY: Optional[str] = None
    GOOGLE_PSE_ENGINE_ID: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None
    KAGI_SEARCH_API_KEY: Optional[str] = None
    MOJEEK_SEARCH_API_KEY: Optional[str] = None
    BOCHA_SEARCH_API_KEY: Optional[str] = None
    SERPSTACK_API_KEY: Optional[str] = None
    SERPSTACK_HTTPS: Optional[bool] = None
    SERPER_API_KEY: Optional[str] = None
    SERPLY_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None
    SEARCHAPI_API_KEY: Optional[str] = None
    SEARCHAPI_ENGINE: Optional[str] = None
    SERPAPI_API_KEY: Optional[str] = None
    SERPAPI_ENGINE: Optional[str] = None
    JINA_API_KEY: Optional[str] = None
    BING_SEARCH_V7_ENDPOINT: Optional[str] = None
    BING_SEARCH_V7_SUBSCRIPTION_KEY: Optional[str] = None
    EXA_API_KEY: Optional[str] = None
    PERPLEXITY_API_KEY: Optional[str] = None
    SOUGOU_API_SID: Optional[str] = None
    SOUGOU_API_SK: Optional[str] = None
    WEB_LOADER_ENGINE: Optional[str] = None
    ENABLE_WEB_LOADER_SSL_VERIFICATION: Optional[bool] = None
    PLAYWRIGHT_WS_URL: Optional[str] = None
    PLAYWRIGHT_TIMEOUT: Optional[int] = None
    FIRECRAWL_API_KEY: Optional[str] = None
    FIRECRAWL_API_BASE_URL: Optional[str] = None
    TAVILY_EXTRACT_DEPTH: Optional[str] = None
    YOUTUBE_LOADER_LANGUAGE: Optional[List[str]] = None
    YOUTUBE_LOADER_PROXY_URL: Optional[str] = None
    YOUTUBE_LOADER_TRANSLATION: Optional[str] = None


class ConfigForm(BaseModel):
    # RAG settings
    RAG_TEMPLATE: Optional[str] = None
    TOP_K: Optional[int] = None
    BYPASS_EMBEDDING_AND_RETRIEVAL: Optional[bool] = None
    RAG_FULL_CONTEXT: Optional[bool] = None

    # Hybrid search settings
    ENABLE_RAG_HYBRID_SEARCH: Optional[bool] = None
    TOP_K_RERANKER: Optional[int] = None
    RELEVANCE_THRESHOLD: Optional[float] = None

    # Content extraction settings
    CONTENT_EXTRACTION_ENGINE: Optional[str] = None
    PDF_EXTRACT_IMAGES: Optional[bool] = None
    TIKA_SERVER_URL: Optional[str] = None
    DOCLING_SERVER_URL: Optional[str] = None
    DOCUMENT_INTELLIGENCE_ENDPOINT: Optional[str] = None
    DOCUMENT_INTELLIGENCE_KEY: Optional[str] = None
    MISTRAL_OCR_API_KEY: Optional[str] = None

    # Chunking settings
    TEXT_SPLITTER: Optional[str] = None
    CHUNK_SIZE: Optional[int] = None
    CHUNK_OVERLAP: Optional[int] = None

    # File upload settings
    FILE_MAX_SIZE: Optional[int] = None
    FILE_MAX_COUNT: Optional[int] = None

    # Integration settings
    ENABLE_GOOGLE_DRIVE_INTEGRATION: Optional[bool] = None
    ENABLE_ONEDRIVE_INTEGRATION: Optional[bool] = None

    # Web search settings
    web: Optional[WebConfig] = None


@router.post("/config/update")
async def update_rag_config(
    request: Request, form_data: ConfigForm, user=Depends(get_admin_user)
):
    # RAG settings
    request.app.state.config.RAG_TEMPLATE = (
        form_data.RAG_TEMPLATE
        if form_data.RAG_TEMPLATE is not None
        else request.app.state.config.RAG_TEMPLATE
    )
    request.app.state.config.TOP_K = (
        form_data.TOP_K
        if form_data.TOP_K is not None
        else request.app.state.config.TOP_K
    )
    request.app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL = (
        form_data.BYPASS_EMBEDDING_AND_RETRIEVAL
        if form_data.BYPASS_EMBEDDING_AND_RETRIEVAL is not None
        else request.app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL
    )
    request.app.state.config.RAG_FULL_CONTEXT = (
        form_data.RAG_FULL_CONTEXT
        if form_data.RAG_FULL_CONTEXT is not None
        else request.app.state.config.RAG_FULL_CONTEXT
    )

    # Hybrid search settings
    request.app.state.config.ENABLE_RAG_HYBRID_SEARCH = (
        form_data.ENABLE_RAG_HYBRID_SEARCH
        if form_data.ENABLE_RAG_HYBRID_SEARCH is not None
        else request.app.state.config.ENABLE_RAG_HYBRID_SEARCH
    )
    # Free up memory if hybrid search is disabled
    if not request.app.state.config.ENABLE_RAG_HYBRID_SEARCH:
        request.app.state.rf = None

    request.app.state.config.TOP_K_RERANKER = (
        form_data.TOP_K_RERANKER
        if form_data.TOP_K_RERANKER is not None
        else request.app.state.config.TOP_K_RERANKER
    )
    request.app.state.config.RELEVANCE_THRESHOLD = (
        form_data.RELEVANCE_THRESHOLD
        if form_data.RELEVANCE_THRESHOLD is not None
        else request.app.state.config.RELEVANCE_THRESHOLD
    )

    # Content extraction settings
    request.app.state.config.CONTENT_EXTRACTION_ENGINE = (
        form_data.CONTENT_EXTRACTION_ENGINE
        if form_data.CONTENT_EXTRACTION_ENGINE is not None
        else request.app.state.config.CONTENT_EXTRACTION_ENGINE
    )
    request.app.state.config.PDF_EXTRACT_IMAGES = (
        form_data.PDF_EXTRACT_IMAGES
        if form_data.PDF_EXTRACT_IMAGES is not None
        else request.app.state.config.PDF_EXTRACT_IMAGES
    )
    request.app.state.config.TIKA_SERVER_URL = (
        form_data.TIKA_SERVER_URL
        if form_data.TIKA_SERVER_URL is not None
        else request.app.state.config.TIKA_SERVER_URL
    )
    request.app.state.config.DOCLING_SERVER_URL = (
        form_data.DOCLING_SERVER_URL
        if form_data.DOCLING_SERVER_URL is not None
        else request.app.state.config.DOCLING_SERVER_URL
    )
    request.app.state.config.DOCUMENT_INTELLIGENCE_ENDPOINT = (
        form_data.DOCUMENT_INTELLIGENCE_ENDPOINT
        if form_data.DOCUMENT_INTELLIGENCE_ENDPOINT is not None
        else request.app.state.config.DOCUMENT_INTELLIGENCE_ENDPOINT
    )
    request.app.state.config.DOCUMENT_INTELLIGENCE_KEY = (
        form_data.DOCUMENT_INTELLIGENCE_KEY
        if form_data.DOCUMENT_INTELLIGENCE_KEY is not None
        else request.app.state.config.DOCUMENT_INTELLIGENCE_KEY
    )
    request.app.state.config.MISTRAL_OCR_API_KEY = (
        form_data.MISTRAL_OCR_API_KEY
        if form_data.MISTRAL_OCR_API_KEY is not None
        else request.app.state.config.MISTRAL_OCR_API_KEY
    )

    # Chunking settings
    request.app.state.config.TEXT_SPLITTER = (
        form_data.TEXT_SPLITTER
        if form_data.TEXT_SPLITTER is not None
        else request.app.state.config.TEXT_SPLITTER
    )
    request.app.state.config.CHUNK_SIZE = (
        form_data.CHUNK_SIZE
        if form_data.CHUNK_SIZE is not None
        else request.app.state.config.CHUNK_SIZE
    )
    request.app.state.config.CHUNK_OVERLAP = (
        form_data.CHUNK_OVERLAP
        if form_data.CHUNK_OVERLAP is not None
        else request.app.state.config.CHUNK_OVERLAP
    )

    # File upload settings
    request.app.state.config.FILE_MAX_SIZE = (
        form_data.FILE_MAX_SIZE
        if form_data.FILE_MAX_SIZE is not None
        else request.app.state.config.FILE_MAX_SIZE
    )
    request.app.state.config.FILE_MAX_COUNT = (
        form_data.FILE_MAX_COUNT
        if form_data.FILE_MAX_COUNT is not None
        else request.app.state.config.FILE_MAX_COUNT
    )

    # Integration settings
    request.app.state.config.ENABLE_GOOGLE_DRIVE_INTEGRATION = (
        form_data.ENABLE_GOOGLE_DRIVE_INTEGRATION
        if form_data.ENABLE_GOOGLE_DRIVE_INTEGRATION is not None
        else request.app.state.config.ENABLE_GOOGLE_DRIVE_INTEGRATION
    )
    request.app.state.config.ENABLE_ONEDRIVE_INTEGRATION = (
        form_data.ENABLE_ONEDRIVE_INTEGRATION
        if form_data.ENABLE_ONEDRIVE_INTEGRATION is not None
        else request.app.state.config.ENABLE_ONEDRIVE_INTEGRATION
    )

    if form_data.web is not None:
        # Web search settings
        request.app.state.config.ENABLE_WEB_SEARCH = form_data.web.ENABLE_WEB_SEARCH
        request.app.state.config.WEB_SEARCH_ENGINE = form_data.web.WEB_SEARCH_ENGINE
        request.app.state.config.WEB_SEARCH_TRUST_ENV = (
            form_data.web.WEB_SEARCH_TRUST_ENV
        )
        request.app.state.config.WEB_SEARCH_RESULT_COUNT = (
            form_data.web.WEB_SEARCH_RESULT_COUNT
        )
        request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS = (
            form_data.web.WEB_SEARCH_CONCURRENT_REQUESTS
        )
        request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST = (
            form_data.web.WEB_SEARCH_DOMAIN_FILTER_LIST
        )
        request.app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = (
            form_data.web.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL
        )
        request.app.state.config.SEARXNG_QUERY_URL = form_data.web.SEARXNG_QUERY_URL
        request.app.state.config.GOOGLE_PSE_API_KEY = form_data.web.GOOGLE_PSE_API_KEY
        request.app.state.config.GOOGLE_PSE_ENGINE_ID = (
            form_data.web.GOOGLE_PSE_ENGINE_ID
        )
        request.app.state.config.BRAVE_SEARCH_API_KEY = (
            form_data.web.BRAVE_SEARCH_API_KEY
        )
        request.app.state.config.KAGI_SEARCH_API_KEY = form_data.web.KAGI_SEARCH_API_KEY
        request.app.state.config.MOJEEK_SEARCH_API_KEY = (
            form_data.web.MOJEEK_SEARCH_API_KEY
        )
        request.app.state.config.BOCHA_SEARCH_API_KEY = (
            form_data.web.BOCHA_SEARCH_API_KEY
        )
        request.app.state.config.SERPSTACK_API_KEY = form_data.web.SERPSTACK_API_KEY
        request.app.state.config.SERPSTACK_HTTPS = form_data.web.SERPSTACK_HTTPS
        request.app.state.config.SERPER_API_KEY = form_data.web.SERPER_API_KEY
        request.app.state.config.SERPLY_API_KEY = form_data.web.SERPLY_API_KEY
        request.app.state.config.TAVILY_API_KEY = form_data.web.TAVILY_API_KEY
        request.app.state.config.SEARCHAPI_API_KEY = form_data.web.SEARCHAPI_API_KEY
        request.app.state.config.SEARCHAPI_ENGINE = form_data.web.SEARCHAPI_ENGINE
        request.app.state.config.SERPAPI_API_KEY = form_data.web.SERPAPI_API_KEY
        request.app.state.config.SERPAPI_ENGINE = form_data.web.SERPAPI_ENGINE
        request.app.state.config.JINA_API_KEY = form_data.web.JINA_API_KEY
        request.app.state.config.BING_SEARCH_V7_ENDPOINT = (
            form_data.web.BING_SEARCH_V7_ENDPOINT
        )
        request.app.state.config.BING_SEARCH_V7_SUBSCRIPTION_KEY = (
            form_data.web.BING_SEARCH_V7_SUBSCRIPTION_KEY
        )
        request.app.state.config.EXA_API_KEY = form_data.web.EXA_API_KEY
        request.app.state.config.PERPLEXITY_API_KEY = form_data.web.PERPLEXITY_API_KEY
        request.app.state.config.SOUGOU_API_SID = form_data.web.SOUGOU_API_SID
        request.app.state.config.SOUGOU_API_SK = form_data.web.SOUGOU_API_SK

        # Web loader settings
        request.app.state.config.WEB_LOADER_ENGINE = form_data.web.WEB_LOADER_ENGINE
        request.app.state.config.ENABLE_WEB_LOADER_SSL_VERIFICATION = (
            form_data.web.ENABLE_WEB_LOADER_SSL_VERIFICATION
        )
        request.app.state.config.PLAYWRIGHT_WS_URL = form_data.web.PLAYWRIGHT_WS_URL
        request.app.state.config.PLAYWRIGHT_TIMEOUT = form_data.web.PLAYWRIGHT_TIMEOUT
        request.app.state.config.FIRECRAWL_API_KEY = form_data.web.FIRECRAWL_API_KEY
        request.app.state.config.FIRECRAWL_API_BASE_URL = (
            form_data.web.FIRECRAWL_API_BASE_URL
        )
        request.app.state.config.TAVILY_EXTRACT_DEPTH = (
            form_data.web.TAVILY_EXTRACT_DEPTH
        )
        request.app.state.config.YOUTUBE_LOADER_LANGUAGE = (
            form_data.web.YOUTUBE_LOADER_LANGUAGE
        )
        request.app.state.config.YOUTUBE_LOADER_PROXY_URL = (
            form_data.web.YOUTUBE_LOADER_PROXY_URL
        )
        request.app.state.YOUTUBE_LOADER_TRANSLATION = (
            form_data.web.YOUTUBE_LOADER_TRANSLATION
        )

    return {
        "status": True,
        # RAG settings
        "RAG_TEMPLATE": request.app.state.config.RAG_TEMPLATE,
        "TOP_K": request.app.state.config.TOP_K,
        "BYPASS_EMBEDDING_AND_RETRIEVAL": request.app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL,
        "RAG_FULL_CONTEXT": request.app.state.config.RAG_FULL_CONTEXT,
        # Hybrid search settings
        "ENABLE_RAG_HYBRID_SEARCH": request.app.state.config.ENABLE_RAG_HYBRID_SEARCH,
        "TOP_K_RERANKER": request.app.state.config.TOP_K_RERANKER,
        "RELEVANCE_THRESHOLD": request.app.state.config.RELEVANCE_THRESHOLD,
        # Content extraction settings
        "CONTENT_EXTRACTION_ENGINE": request.app.state.config.CONTENT_EXTRACTION_ENGINE,
        "PDF_EXTRACT_IMAGES": request.app.state.config.PDF_EXTRACT_IMAGES,
        "TIKA_SERVER_URL": request.app.state.config.TIKA_SERVER_URL,
        "DOCLING_SERVER_URL": request.app.state.config.DOCLING_SERVER_URL,
        "DOCUMENT_INTELLIGENCE_ENDPOINT": request.app.state.config.DOCUMENT_INTELLIGENCE_ENDPOINT,
        "DOCUMENT_INTELLIGENCE_KEY": request.app.state.config.DOCUMENT_INTELLIGENCE_KEY,
        "MISTRAL_OCR_API_KEY": request.app.state.config.MISTRAL_OCR_API_KEY,
        # Chunking settings
        "TEXT_SPLITTER": request.app.state.config.TEXT_SPLITTER,
        "CHUNK_SIZE": request.app.state.config.CHUNK_SIZE,
        "CHUNK_OVERLAP": request.app.state.config.CHUNK_OVERLAP,
        # File upload settings
        "FILE_MAX_SIZE": request.app.state.config.FILE_MAX_SIZE,
        "FILE_MAX_COUNT": request.app.state.config.FILE_MAX_COUNT,
        # Integration settings
        "ENABLE_GOOGLE_DRIVE_INTEGRATION": request.app.state.config.ENABLE_GOOGLE_DRIVE_INTEGRATION,
        "ENABLE_ONEDRIVE_INTEGRATION": request.app.state.config.ENABLE_ONEDRIVE_INTEGRATION,
        # Web search settings
        "web": {
            "ENABLE_WEB_SEARCH": request.app.state.config.ENABLE_WEB_SEARCH,
            "WEB_SEARCH_ENGINE": request.app.state.config.WEB_SEARCH_ENGINE,
            "WEB_SEARCH_TRUST_ENV": request.app.state.config.WEB_SEARCH_TRUST_ENV,
            "WEB_SEARCH_RESULT_COUNT": request.app.state.config.WEB_SEARCH_RESULT_COUNT,
            "WEB_SEARCH_CONCURRENT_REQUESTS": request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS,
            "WEB_SEARCH_DOMAIN_FILTER_LIST": request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST,
            "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL": request.app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL,
            "SEARXNG_QUERY_URL": request.app.state.config.SEARXNG_QUERY_URL,
            "GOOGLE_PSE_API_KEY": request.app.state.config.GOOGLE_PSE_API_KEY,
            "GOOGLE_PSE_ENGINE_ID": request.app.state.config.GOOGLE_PSE_ENGINE_ID,
            "BRAVE_SEARCH_API_KEY": request.app.state.config.BRAVE_SEARCH_API_KEY,
            "KAGI_SEARCH_API_KEY": request.app.state.config.KAGI_SEARCH_API_KEY,
            "MOJEEK_SEARCH_API_KEY": request.app.state.config.MOJEEK_SEARCH_API_KEY,
            "BOCHA_SEARCH_API_KEY": request.app.state.config.BOCHA_SEARCH_API_KEY,
            "SERPSTACK_API_KEY": request.app.state.config.SERPSTACK_API_KEY,
            "SERPSTACK_HTTPS": request.app.state.config.SERPSTACK_HTTPS,
            "SERPER_API_KEY": request.app.state.config.SERPER_API_KEY,
            "SERPLY_API_KEY": request.app.state.config.SERPLY_API_KEY,
            "TAVILY_API_KEY": request.app.state.config.TAVILY_API_KEY,
            "SEARCHAPI_API_KEY": request.app.state.config.SEARCHAPI_API_KEY,
            "SEARCHAPI_ENGINE": request.app.state.config.SEARCHAPI_ENGINE,
            "SERPAPI_API_KEY": request.app.state.config.SERPAPI_API_KEY,
            "SERPAPI_ENGINE": request.app.state.config.SERPAPI_ENGINE,
            "JINA_API_KEY": request.app.state.config.JINA_API_KEY,
            "BING_SEARCH_V7_ENDPOINT": request.app.state.config.BING_SEARCH_V7_ENDPOINT,
            "BING_SEARCH_V7_SUBSCRIPTION_KEY": request.app.state.config.BING_SEARCH_V7_SUBSCRIPTION_KEY,
            "EXA_API_KEY": request.app.state.config.EXA_API_KEY,
            "PERPLEXITY_API_KEY": request.app.state.config.PERPLEXITY_API_KEY,
            "SOUGOU_API_SID": request.app.state.config.SOUGOU_API_SID,
            "SOUGOU_API_SK": request.app.state.config.SOUGOU_API_SK,
            "WEB_LOADER_ENGINE": request.app.state.config.WEB_LOADER_ENGINE,
            "ENABLE_WEB_LOADER_SSL_VERIFICATION": request.app.state.config.ENABLE_WEB_LOADER_SSL_VERIFICATION,
            "PLAYWRIGHT_WS_URL": request.app.state.config.PLAYWRIGHT_WS_URL,
            "PLAYWRIGHT_TIMEOUT": request.app.state.config.PLAYWRIGHT_TIMEOUT,
            "FIRECRAWL_API_KEY": request.app.state.config.FIRECRAWL_API_KEY,
            "FIRECRAWL_API_BASE_URL": request.app.state.config.FIRECRAWL_API_BASE_URL,
            "TAVILY_EXTRACT_DEPTH": request.app.state.config.TAVILY_EXTRACT_DEPTH,
            "YOUTUBE_LOADER_LANGUAGE": request.app.state.config.YOUTUBE_LOADER_LANGUAGE,
            "YOUTUBE_LOADER_PROXY_URL": request.app.state.config.YOUTUBE_LOADER_PROXY_URL,
            "YOUTUBE_LOADER_TRANSLATION": request.app.state.YOUTUBE_LOADER_TRANSLATION,
        },
    }


####################################
#
# Document process and retrieval
#
####################################


def save_docs_to_vector_db(
    request: Request,
    docs,
    collection_name,
    metadata: Optional[dict] = None,
    overwrite: bool = False,
    split: bool = True,
    add: bool = False,
    user=None,
) -> bool:
    def _get_docs_info(docs: list[Document]) -> str:
        docs_info = set()

        # Trying to select relevant metadata identifying the document.
        for doc in docs:
            metadata = getattr(doc, "metadata", {})
            doc_name = metadata.get("name", "")
            if not doc_name:
                doc_name = metadata.get("title", "")
            if not doc_name:
                doc_name = metadata.get("source", "")
            if doc_name:
                docs_info.add(doc_name)

        return ", ".join(docs_info)

    log.info(
        f"save_docs_to_vector_db: document {_get_docs_info(docs)} {collection_name}"
    )

    # Check if entries with the same hash (metadata.hash) already exist
    if metadata and "hash" in metadata:
        result = VECTOR_DB_CLIENT.query(
            collection_name=collection_name,
            filter={"hash": metadata["hash"]},
        )

        if result is not None:
            existing_doc_ids = result.ids[0]
            if existing_doc_ids:
                log.info(f"Document with hash {metadata['hash']} already exists")
                raise ValueError(ERROR_MESSAGES.DUPLICATE_CONTENT)

    if split:
        if request.app.state.config.TEXT_SPLITTER in ["", "character"]:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=request.app.state.config.CHUNK_SIZE,
                chunk_overlap=request.app.state.config.CHUNK_OVERLAP,
                add_start_index=True,
            )
        elif request.app.state.config.TEXT_SPLITTER == "token":
            log.info(
                f"Using token text splitter: {request.app.state.config.TIKTOKEN_ENCODING_NAME}"
            )

            tiktoken.get_encoding(str(request.app.state.config.TIKTOKEN_ENCODING_NAME))
            text_splitter = TokenTextSplitter(
                encoding_name=str(request.app.state.config.TIKTOKEN_ENCODING_NAME),
                chunk_size=request.app.state.config.CHUNK_SIZE,
                chunk_overlap=request.app.state.config.CHUNK_OVERLAP,
                add_start_index=True,
            )
        else:
            raise ValueError(ERROR_MESSAGES.DEFAULT("Invalid text splitter"))

        docs = text_splitter.split_documents(docs)

    if len(docs) == 0:
        raise ValueError(ERROR_MESSAGES.EMPTY_CONTENT)

    texts = [doc.page_content for doc in docs]
    metadatas = [
        {
            **doc.metadata,
            **(metadata if metadata else {}),
            "embedding_config": json.dumps(
                {
                    "engine": request.app.state.config.RAG_EMBEDDING_ENGINE,
                    "model": request.app.state.config.RAG_EMBEDDING_MODEL,
                }
            ),
        }
        for doc in docs
    ]

    # ChromaDB does not like datetime formats
    # for meta-data so convert them to string.
    for metadata in metadatas:
        for key, value in metadata.items():
            if (
                isinstance(value, datetime)
                or isinstance(value, list)
                or isinstance(value, dict)
            ):
                metadata[key] = str(value)

    try:
        if VECTOR_DB_CLIENT.has_collection(collection_name=collection_name):
            log.info(f"collection {collection_name} already exists")

            if overwrite:
                VECTOR_DB_CLIENT.delete_collection(collection_name=collection_name)
                log.info(f"deleting existing collection {collection_name}")
            elif add is False:
                log.info(
                    f"collection {collection_name} already exists, overwrite is False and add is False"
                )
                return True

        log.info(f"adding to collection {collection_name}")
        embedding_function = get_embedding_function(
            request.app.state.config.RAG_EMBEDDING_ENGINE,
            request.app.state.config.RAG_EMBEDDING_MODEL,
            request.app.state.ef,
            (
                request.app.state.config.RAG_OPENAI_API_BASE_URL
                if request.app.state.config.RAG_EMBEDDING_ENGINE == "openai"
                else request.app.state.config.RAG_OLLAMA_BASE_URL
            ),
            (
                request.app.state.config.RAG_OPENAI_API_KEY
                if request.app.state.config.RAG_EMBEDDING_ENGINE == "openai"
                else request.app.state.config.RAG_OLLAMA_API_KEY
            ),
            request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
        )

        embeddings = embedding_function(
            list(map(lambda x: x.replace("\n", " "), texts)),
            prefix=RAG_EMBEDDING_CONTENT_PREFIX,
            user=user,
        )

        items = [
            {
                "id": str(uuid.uuid4()),
                "text": text,
                "vector": embeddings[idx],
                "metadata": metadatas[idx],
            }
            for idx, text in enumerate(texts)
        ]

        VECTOR_DB_CLIENT.insert(
            collection_name=collection_name,
            items=items,
        )

        return True
    except Exception as e:
        log.exception(e)
        raise e


class ProcessFileForm(BaseModel):
    file_id: str
    content: Optional[str] = None
    collection_name: Optional[str] = None


@router.post("/process/file")
def process_file(
    request: Request,
    form_data: ProcessFileForm,
    user=Depends(get_verified_user),
):
    try:
        file = Files.get_file_by_id(form_data.file_id)

        collection_name = form_data.collection_name

        if collection_name is None:
            collection_name = f"file-{file.id}"

        if form_data.content:
            # Update the content in the file
            # Usage: /files/{file_id}/data/content/update, /files/ (audio file upload pipeline)

            try:
                # /files/{file_id}/data/content/update
                VECTOR_DB_CLIENT.delete_collection(collection_name=f"file-{file.id}")
            except:
                # Audio file upload pipeline
                pass

            docs = [
                Document(
                    page_content=form_data.content.replace("<br/>", "\n"),
                    metadata={
                        **file.meta,
                        "name": file.filename,
                        "created_by": file.user_id,
                        "file_id": file.id,
                        "source": file.filename,
                    },
                )
            ]

            text_content = form_data.content
        elif form_data.collection_name:
            # Check if the file has already been processed and save the content
            # Usage: /knowledge/{id}/file/add, /knowledge/{id}/file/update

            result = VECTOR_DB_CLIENT.query(
                collection_name=f"file-{file.id}", filter={"file_id": file.id}
            )

            if result is not None and len(result.ids[0]) > 0:
                docs = [
                    Document(
                        page_content=result.documents[0][idx],
                        metadata=result.metadatas[0][idx],
                    )
                    for idx, id in enumerate(result.ids[0])
                ]
            else:
                docs = [
                    Document(
                        page_content=file.data.get("content", ""),
                        metadata={
                            **file.meta,
                            "name": file.filename,
                            "created_by": file.user_id,
                            "file_id": file.id,
                            "source": file.filename,
                        },
                    )
                ]

            text_content = file.data.get("content", "")
        else:
            # Process the file and save the content
            # Usage: /files/
            file_path = file.path
            if file_path:
                file_path = Storage.get_file(file_path)
                loader = Loader(
                    engine=request.app.state.config.CONTENT_EXTRACTION_ENGINE,
                    TIKA_SERVER_URL=request.app.state.config.TIKA_SERVER_URL,
                    DOCLING_SERVER_URL=request.app.state.config.DOCLING_SERVER_URL,
                    PDF_EXTRACT_IMAGES=request.app.state.config.PDF_EXTRACT_IMAGES,
                    DOCUMENT_INTELLIGENCE_ENDPOINT=request.app.state.config.DOCUMENT_INTELLIGENCE_ENDPOINT,
                    DOCUMENT_INTELLIGENCE_KEY=request.app.state.config.DOCUMENT_INTELLIGENCE_KEY,
                    MISTRAL_OCR_API_KEY=request.app.state.config.MISTRAL_OCR_API_KEY,
                )
                docs = loader.load(
                    file.filename, file.meta.get("content_type"), file_path
                )

                docs = [
                    Document(
                        page_content=doc.page_content,
                        metadata={
                            **doc.metadata,
                            "name": file.filename,
                            "created_by": file.user_id,
                            "file_id": file.id,
                            "source": file.filename,
                        },
                    )
                    for doc in docs
                ]
            else:
                docs = [
                    Document(
                        page_content=file.data.get("content", ""),
                        metadata={
                            **file.meta,
                            "name": file.filename,
                            "created_by": file.user_id,
                            "file_id": file.id,
                            "source": file.filename,
                        },
                    )
                ]
            text_content = " ".join([doc.page_content for doc in docs])

        log.debug(f"text_content: {text_content}")
        Files.update_file_data_by_id(
            file.id,
            {"content": text_content},
        )

        hash = calculate_sha256_string(text_content)
        Files.update_file_hash_by_id(file.id, hash)

        if not request.app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL:
            try:
                result = save_docs_to_vector_db(
                    request,
                    docs=docs,
                    collection_name=collection_name,
                    metadata={
                        "file_id": file.id,
                        "name": file.filename,
                        "hash": hash,
                    },
                    add=(True if form_data.collection_name else False),
                    user=user,
                )

                if result:
                    Files.update_file_metadata_by_id(
                        file.id,
                        {
                            "collection_name": collection_name,
                        },
                    )

                    return {
                        "status": True,
                        "collection_name": collection_name,
                        "filename": file.filename,
                        "content": text_content,
                    }
            except Exception as e:
                raise e
        else:
            return {
                "status": True,
                "collection_name": None,
                "filename": file.filename,
                "content": text_content,
            }

    except Exception as e:
        log.exception(e)
        if "No pandoc was found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.PANDOC_NOT_INSTALLED,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )


class ProcessTextForm(BaseModel):
    name: str
    content: str
    collection_name: Optional[str] = None


@router.post("/process/text")
def process_text(
    request: Request,
    form_data: ProcessTextForm,
    user=Depends(get_verified_user),
):
    collection_name = form_data.collection_name
    if collection_name is None:
        collection_name = calculate_sha256_string(form_data.content)

    docs = [
        Document(
            page_content=form_data.content,
            metadata={"name": form_data.name, "created_by": user.id},
        )
    ]
    text_content = form_data.content
    log.debug(f"text_content: {text_content}")

    result = save_docs_to_vector_db(request, docs, collection_name, user=user)
    if result:
        return {
            "status": True,
            "collection_name": collection_name,
            "content": text_content,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(),
        )


@router.post("/process/youtube")
def process_youtube_video(
    request: Request, form_data: ProcessUrlForm, user=Depends(get_verified_user)
):
    try:
        collection_name = form_data.collection_name
        if not collection_name:
            collection_name = calculate_sha256_string(form_data.url)[:63]

        loader = YoutubeLoader(
            form_data.url,
            language=request.app.state.config.YOUTUBE_LOADER_LANGUAGE,
            proxy_url=request.app.state.config.YOUTUBE_LOADER_PROXY_URL,
        )

        docs = loader.load()
        content = " ".join([doc.page_content for doc in docs])
        log.debug(f"text_content: {content}")

        save_docs_to_vector_db(
            request, docs, collection_name, overwrite=True, user=user
        )

        return {
            "status": True,
            "collection_name": collection_name,
            "filename": form_data.url,
            "file": {
                "data": {
                    "content": content,
                },
                "meta": {
                    "name": form_data.url,
                },
            },
        }
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


ALLOWED_ENGINES = set(ENGINES.keys())
DEFAULT_ENGINE = (
    os.getenv("WEB_SEARCH_ENGINE", "google_pse").lower()
    if os.getenv("WEB_SEARCH_ENGINE", "").lower() in ALLOWED_ENGINES
    else "google_pse"
)

PARALLEL_ENGINES = {
    "exa", "google_pse", "jina", "searchapi", "serper", "serply",
    "serpstack", "tavily", "serpapi", "bocha"
}

LEGACY_FN_NAME = {
    "bing": "search_bing",
    "brave": "search_brave",
    "duckduckgo": "search_duckduckgo",
    "kagi": "search_kagi",
    "mojeek": "search_mojeek",
    "perplexity": "search_perplexity",
    "sougou": "search_sougou",
    "searxng": "search_searxng",

    "google_pse": "search_google_pse",
    "exa": "search_exa",
    "jina": "search_jina",
    "searchapi": "search_searchapi",
    "serper": "search_serper",
    "serply": "search_serply",
    "serpstack": "search_serpstack",
    "tavily": "search_tavily",
    "serpapi": "search_serpapi",
    "bocha": "search_bocha",
}

class WebSearchLinksForm(BaseModel):
    q: str
    engine: Optional[str] = None
    limit: int = 30
    page_size: int = 10
    max_page_concurrency: int = 3
    timeout: float = 10.0
    filter_list: List[str] = Field(default_factory=list, example=[])
    extra: Dict[str, Any] = Field(default_factory=dict, example={})

log = logging.getLogger("web.search")

def _read_persistent(cfg_item):
    if hasattr(cfg_item, "get"):
        try:
            return cfg_item.get()
        except Exception:
            pass
    if hasattr(cfg_item, "value"):
        try:
            return cfg_item.value
        except Exception:
            pass
    return cfg_item

def _effective_engine(config) -> str:
    raw = _read_persistent(getattr(config, "WEB_SEARCH_ENGINE", None))
    eng = (raw or "").strip().lower()
    if eng not in ALLOWED_ENGINES:
        log.warning("[search] Unsupported engine %r, fallback -> %r", eng, DEFAULT_ENGINE)
        return DEFAULT_ENGINE
    return eng

def _filter_kwargs_for_callable(fn, kwargs: dict) -> dict:
    try:
        sig = inspect.signature(fn)
        if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            return {k: v for k, v in kwargs.items() if v is not None}
        names = set(sig.parameters.keys())
        return {k: v for k, v in kwargs.items() if (k in names and v is not None)}
    except Exception:
        return {}

def cfg_get(cfg, name: str, default=None):
    v = getattr(cfg, name, None)
    if v is None:
        return default
    try:
        return v.get()
    except Exception:
        return v

def _build_engine_extras_from_config(cfg, engine: str) -> dict:
    e = engine.lower().strip()
    x: Dict[str, Any] = {}
    if e == "searxng":
        x["query_url"] = getattr(cfg, "SEARXNG_QUERY_URL", None)
    elif e == "google_pse":
        x["api_key"] = getattr(cfg, "GOOGLE_PSE_API_KEY", None)
        x["engine_id"] = getattr(cfg, "GOOGLE_PSE_ENGINE_ID", None) or getattr(cfg, "GOOGLE_CX", None)
    elif e == "brave":
        x["api_key"] = getattr(cfg, "BRAVE_SEARCH_API_KEY", None)
    elif e == "kagi":
        x["api_key"] = getattr(cfg, "KAGI_SEARCH_API_KEY", None)
    elif e == "mojeek":
        x["api_key"] = getattr(cfg, "MOJEEK_SEARCH_API_KEY", None)
    elif e == "bocha":
        x["api_key"] = getattr(cfg, "BOCHA_SEARCH_API_KEY", None)
    elif e == "serpstack":
        x["api_key"] = getattr(cfg, "SERPSTACK_API_KEY", None)
        x["https_enabled"] = getattr(cfg, "SERPSTACK_HTTPS", None)
    elif e == "serper":
        x["api_key"] = getattr(cfg, "SERPER_API_KEY", None)
    elif e == "serply":
        x["api_key"] = getattr(cfg, "SERPLY_API_KEY", None)
    elif e == "tavily":
        x["api_key"] = getattr(cfg, "TAVILY_API_KEY", None)
        x["extract_depth"] = getattr(cfg, "TAVILY_EXTRACT_DEPTH", None)
    elif e == "exa":
        x["api_key"] = getattr(cfg, "EXA_API_KEY", None)
    elif e == "perplexity":
        x["api_key"] = getattr(cfg, "PERPLEXITY_API_KEY", None)
    elif e == "sougou":
        x["sid"] = getattr(cfg, "SOUGOU_API_SID", None)
        x["sk"] = getattr(cfg, "SOUGOU_API_SK", None)
    elif e == "searchapi":
        x["api_key"] = getattr(cfg, "SEARCHAPI_API_KEY", None)
        x["engine"] = getattr(cfg, "SEARCHAPI_ENGINE", None)
        x["endpoint"] = getattr(cfg, "SEARCHAPI_ENDPOINT", None)
    elif e == "serpapi":
        x["api_key"] = getattr(cfg, "SERPAPI_API_KEY", None)
        x["engine"] = getattr(cfg, "SERPAPI_ENGINE", None)
    elif e == "jina":
        x["api_key"] = getattr(cfg, "JINA_API_KEY", None)
    elif e == "bing":
        x["subscription_key"] = getattr(cfg, "BING_SEARCH_V7_SUBSCRIPTION_KEY", None)
        x["endpoint"] = getattr(cfg, "BING_SEARCH_V7_ENDPOINT", None)
        x["mkt"] = str(DEFAULT_LOCALE)
    return {k: v for k, v in x.items() if v not in (None, "", False)}

def _prepare_call_kwargs_with_concurrency(fn, base: dict) -> dict:
    sig = inspect.signature(fn)
    params = sig.parameters
    allow_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())
    v = base.get("max_page_concurrency", None)
    call_kwargs = dict(base)
    if "max_page_concurrency" in call_kwargs:
        del call_kwargs["max_page_concurrency"]
    if v is not None:
        for name in ("max_page_concurrency", "max_variant_concurrency", "max_concurrency", "concurrency"):
            if allow_kwargs or (name in params):
                call_kwargs[name] = v
                break
    return _filter_kwargs_for_callable(fn, call_kwargs)

async def _maybe_await(fn, **kwargs):
    if inspect.iscoroutinefunction(fn):
        return await fn(**kwargs)
    return await run_in_threadpool(fn, **kwargs)

def _domain_of(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""

def dedupe_urls(urls: List[str], keep_per_domain: int = 3) -> List[str]:
    seen = set()
    buckets = defaultdict(list)
    out: List[str] = []
    for u in urls:
        if not u or u in seen:
            continue
        d = _domain_of(u)
        if len(buckets[d]) < keep_per_domain:
            buckets[d].append(u)
            seen.add(u)
            out.append(u)
    return out

def _trim_by_tokens(text: str, max_tokens: int, encoding_name: Optional[str]) -> str:
    try:
        enc = tiktoken.get_encoding(str(encoding_name)) if encoding_name else tiktoken.get_encoding("cl100k_base")
        toks = enc.encode(text or "")
        if len(toks) <= max_tokens:
            return text or ""
        return enc.decode(toks[:max_tokens])
    except Exception:
        return (text or "")[: max_tokens * 4]

def _sanitize_mode(s: str | None) -> str:
    v = (s or "").strip().lower()
    if v in {"", "string", "none", "null", "default", "auto"}:
        return ""
    return v

MIN_OK_LEN = 500

def _normalize_url(u: str) -> str:
    if not u:
        return ""
    try:
        p = urlparse(u)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k.lower() not in {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid"}]
        p = p._replace(fragment="", query=urlencode(q, doseq=True))
        return urlunparse(p)
    except Exception:
        return u.split("#")[0]

_PDF_POSITIVE = re.compile(r'(?i)(^|\s)(?<!-)(?:filetype|ext)\s*:\s*pdf\b')

def _to_r2_query(q: str) -> str:

    q2 = _PDF_POSITIVE.sub(' ', q or '')
    q2 = re.sub(r'\s+', ' ', q2).strip()

    if '-filetype:pdf' not in q2.lower():
        q2 = f'{q2} -filetype:pdf'
    return q2

def _make_variants(q: str, n: int = 2) -> List[str]:
    base = (q or '').strip()
    if not base:
        return []
    cands = [
        base,  
        _to_r2_query(base),  
        f'"{base}"',
        f'{base} site:dev.to OR site:medium.com',
    ]
    out, seen = [], set()
    for v in cands:
        if v not in seen:
            seen.add(v); out.append(v)
        if len(out) >= max(1, n):
            break
    return out

MIN_OK_LEN = 400 
ANTI_BOT_KEYWORDS = (
    "captcha", "verify you are human", "checking your browser",
    "access denied", "forbidden", "just a moment", "cloudflare",
    "akamai", "perimeterx"
)

def _looks_bot_blocked_text(text: str) -> bool:
    t = (text or "").lower()
    if len(t) < MIN_OK_LEN:
        return True
    return any(k in t for k in ANTI_BOT_KEYWORDS)


async def _fetch_one_with_crawl4ai_fallback(
    request: Request,
    url: str,
    timeout_s: float,
    user_agent: str,
    verify_ssl: bool,
    rps: int,
    trust_env: bool,
):
    try:
        docs = await _crawl4ai_fetch_docs(
            request, [url],
            timeout_sec=timeout_s,
            concurrency=1,
            user_agent=user_agent,
        )
        if not docs or not docs[0] or not getattr(docs[0], "metadata", None) or not docs[0].metadata.get("source"):
            log.debug("[crawl4ai-only] empty -> skip url=%s", url)
            return None

        content = (docs[0].page_content or "").strip()

        if _looks_bot_blocked_text(content):
            log.info("[antibot] blocked/too-short -> skip url=%s len=%s", url, len(content))
            return None

        return docs[0]

    except Exception as e:
        log.debug("[crawl4ai-only] %s -> skip url=%s", e, url)
        return None


async def _engine_search_links(
    request: Request,
    engine: str,
    q: str,
    *,
    limit: int,
    page_size: int,
    timeout: float,
    max_page_concurrency: int,
    filter_list: List[str],
    extra: Optional[Dict[str, Any]] = None,
) -> List[SearchResult]:
    mod = ENGINES[engine]
    extras_cfg = _build_engine_extras_from_config(request.app.state.config, engine)
    extras = {**extras_cfg, **(extra or {})}

    if engine not in PARALLEL_ENGINES:
        max_page_concurrency = 1

    fn_many = getattr(mod, "search_many_links", None)
    if engine in PARALLEL_ENGINES and callable(fn_many):
        base = dict(q=q, limit=limit, timeout=timeout, page_size=page_size,
                    max_page_concurrency=max_page_concurrency,
                    filter_list=filter_list, **extras)
        call_kwargs = _prepare_call_kwargs_with_concurrency(fn_many, base)
        return await _maybe_await(fn_many, **call_kwargs)
    
    legacy_name = LEGACY_FN_NAME.get(engine)
    fn = getattr(mod, legacy_name, None) if legacy_name else None
    if fn is None and callable(fn_many):

        base = dict(q=q, limit=limit, timeout=timeout, page_size=page_size,
                    max_page_concurrency=1, filter_list=filter_list, **extras)
        call_kwargs = _prepare_call_kwargs_with_concurrency(fn_many, base)
        return await _maybe_await(fn_many, **call_kwargs)

    if fn is None:
        raise RuntimeError(f"Engine '{engine}' doesn't provide search_many_links or legacy search function")

    legacy_kwargs = dict(
        query=q,
        q=q,
        count=limit,
        limit=limit,
        page_size=page_size,
        timeout=timeout,
        filter_list=filter_list,
        **extras,
    )
    legacy_kwargs = _filter_kwargs_for_callable(fn, legacy_kwargs)
    return await _maybe_await(fn, **legacy_kwargs)

async def search_web_async(
    request: Request,
    engine: str,
    query: str,
    *,
    limit: Optional[int] = None,
    page_size: Optional[int] = None,
    max_conc: Optional[int] = None,
    run_id: Optional[str] = None,
) -> List[SearchResult]:
    cfg = request.app.state.config
    if engine not in ENGINES:
        log.warning("Unsupported engine %r; fallback to %r", engine, DEFAULT_ENGINE)
        engine = DEFAULT_ENGINE

    timeout = 10.0

    if limit is None:
        limit = int(cfg_get(cfg, "WEB_SEARCH_RESULT_COUNT", 30))
    if page_size is None:
        page_size = int(cfg_get(cfg, "WEB_SEARCH_PAGE_SIZE", 10))
    if max_conc is None:
        max_conc = int(cfg_get(cfg, "WEB_SEARCH_CONCURRENT_REQUESTS", 3))

    limit = max(1, min(int(limit), 100))
    page_size = max(1, min(int(page_size), 10))
    max_conc = max(1, min(int(max_conc), 10))
    filter_list = request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST

    expected_pages = (limit + page_size - 1) // page_size

    rid = run_id or uuid.uuid4().hex[:6]
    log.info("[search_async#%s] engine=%s q=%r limit=%s page_size=%s -> pages=%s max_conc=%s",
             rid, engine, query, limit, page_size, expected_pages, max_conc)

    results = await _engine_search_links(
        request, engine, query,
        limit=limit, page_size=page_size, timeout=timeout,
        max_page_concurrency=max_conc, filter_list=filter_list, extra=None
    )

    if len(results) > limit:
        results = results[:limit]
    log.info("[search_async#%s] engine=%s got %s links (limit=%s)", rid, engine, len(results), limit)
    return results

@router.post("/process/web")
async def process_web(request: Request, form_data: ProcessUrlForm, user=Depends(get_verified_user)):
    try:
        collection_name = form_data.collection_name or calculate_sha256_string(form_data.url)[:63]

        try:
            cfg_mode_raw = request.app.state.config.WEB_LOADER_ENGINE.get()
        except Exception:
            cfg_mode_raw = getattr(request.app.state.config, "WEB_LOADER_ENGINE", None)
        cfg_mode = _sanitize_mode(cfg_mode_raw)
        env_mode = _sanitize_mode(os.getenv("WEB_LOADER_ENGINE"))
        mode = cfg_mode or env_mode or "crawl4ai"
        use_crawl4ai = (mode == "crawl4ai")

        if use_crawl4ai:
            docs = await _crawl4ai_fetch_docs(
                request,
                [form_data.url],
                timeout_sec=float(request.app.state.config.PLAYWRIGHT_TIMEOUT or 15000) / 1000.0,
                concurrency=int(request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS or 3),
                user_agent="Open WebUI (Crawl4AI)",
            )
        else:
            loader = get_web_loader(
                form_data.url,
                verify_ssl=request.app.state.config.ENABLE_WEB_LOADER_SSL_VERIFICATION,
                requests_per_second=request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS,
            )
            docs = await loader.aload()

        content = " ".join([doc.page_content for doc in docs if doc and getattr(doc, "page_content", None)])

        if not request.app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL:
            await run_in_threadpool(save_docs_to_vector_db, request, docs, collection_name, True, user)
        else:
            collection_name = None

        if request.app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL and (use_crawl4ai):
            return {
                "status": True,
                "collection_name": None,
                "filename": form_data.url,
                "loaded_count": len(docs),
                "docs": [
                    {
                        "title": d.metadata.get("title"),
                        "source": d.metadata.get("source"),
                        "loader": d.metadata.get("loader"),
                        "structured": d.metadata.get("structured"),
                        "content": (d.page_content or "")[:300] + "...",
                    }
                    for d in docs if d
                ],
            }

        return {
            "status": True,
            "collection_name": collection_name,
            "filename": form_data.url,
            "file": {
                "data": {"content": content},
                "meta": {"name": form_data.url, "source": form_data.url},
            },
        }
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT(e))

@router.post("/process/web/search_links")
async def process_web_search_links(request: Request, form: WebSearchLinksForm, user=Depends(get_verified_user)):
    cfg_engine = form.engine or _read_persistent(getattr(request.app.state.config, "WEB_SEARCH_ENGINE", None))
    engine = (cfg_engine or "").strip().lower()
    if engine not in ALLOWED_ENGINES:
        engine = DEFAULT_ENGINE

    try:
        filter_list = form.filter_list or request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST
        results = await _engine_search_links(
            request, engine, form.q,
            limit=int(form.limit), page_size=int(form.page_size),
            timeout=float(form.timeout),
            max_page_concurrency=int(form.max_page_concurrency),
            filter_list=filter_list,
            extra=form.extra or {},
        )
        return {
            "status": True,
            "engine": engine,
            "count": len(results),
            "results": [r.dict() if hasattr(r, "dict") else r for r in results],
        }
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.WEB_SEARCH_ERROR(e))

@router.post("/process/web/search")
async def process_web_search(request: Request, form_data: SearchForm, user=Depends(get_verified_user)):
    engine = _effective_engine(request.app.state.config)
    
    eff_limit = int(form_data.limit) if form_data.limit is not None else int(getattr(request.app.state.config, "WEB_SEARCH_RESULT_COUNT", 30) or 30)
    if eff_limit < 1: eff_limit = 1
    if eff_limit > 100: eff_limit = 100

    run_id = uuid.uuid4().hex[:6]

    try:
        web_results = await search_web_async(
            request, engine, form_data.query,
            limit=eff_limit,
            page_size=form_data.page_size, 
            max_conc=form_data.concurrency,
            run_id=run_id, 
        )
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.WEB_SEARCH_ERROR(e))

    try:
        urls = [result.link for result in web_results]
        keep_per_domain = 3
        urls = dedupe_urls(urls, keep_per_domain=keep_per_domain)
        top_k_fetch = int(getattr(request.app.state.config, "WEB_FETCH_TOP_K", 0) or 15)
        urls = urls[:min(top_k_fetch, eff_limit)]
        if not urls:
            return {"status": True, "collection_name": None, "filenames": [], "loaded_count": 0, "docs": []}

        cfg = request.app.state.config
        bypass = bool(
            getattr(cfg, "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL", None)
            if getattr(cfg, "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL", None) is not None
            else getattr(cfg, "BYPASS_EMBEDDING_AND_RETRIEVAL", False)
        )

        try:
            cfg_mode_raw = cfg.WEB_LOADER_ENGINE.get()
        except Exception:
            cfg_mode_raw = getattr(cfg, "WEB_LOADER_ENGINE", None)
        cfg_mode = _sanitize_mode(cfg_mode_raw)
        env_mode = _sanitize_mode(os.getenv("WEB_LOADER_ENGINE"))
        mode = cfg_mode or env_mode or "crawl4ai"
        use_crawl4ai = (mode == "crawl4ai")

        timeout_s = max(5.0, float(getattr(cfg, "PLAYWRIGHT_TIMEOUT", 15000)) / 1000.0)
        verify_ssl = bool(getattr(cfg, "ENABLE_WEB_LOADER_SSL_VERIFICATION", True))
        trust_env = bool(getattr(cfg, "WEB_SEARCH_TRUST_ENV", False))
        concurrency = max(1, int(form_data.concurrency) if form_data.concurrency is not None else int(getattr(cfg, "WEB_SEARCH_CONCURRENT_REQUESTS", 3) or 3))
        rps = concurrency

        if use_crawl4ai:
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            sem = asyncio.Semaphore(concurrency)

            durations: list[float] = []
            queue_waits: list[float] = []

            def _label(i, u):
                from urllib.parse import urlparse
                try:
                    host = urlparse(u).netloc or u
                except Exception:
                    host = u
                return f"u{i}@{host}"

            async def _guarded(i: int, u: str):
                t_enq = loop.time()
                log.info(f"[crawl4ai#{run_id}] ENQ  { _label(i,u) } +{t_enq - t0:.2f}s")

                async with sem:
                    t_acq = loop.time()
                    qwait = t_acq - t_enq
                    log.info(f"[crawl4ai#{run_id}] START { _label(i,u) } +{t_acq - t0:.2f}s (queue_wait={qwait:.2f}s)")
                    try:
                        doc = await _fetch_one_with_crawl4ai_fallback(
                            request=request, url=u, timeout_s=timeout_s,
                            user_agent="Open WebUI (Crawl4AI)",
                            verify_ssl=verify_ssl, rps=rps, trust_env=trust_env,
                        )
                        t_end = loop.time()
                        dur = t_end - t_acq
                        ok = bool(doc and getattr(doc, "metadata", None) and doc.metadata.get("source"))
                        log.info(f"[crawl4ai#{run_id}] DONE  { _label(i,u) } +{t_end - t0:.2f}s (dur={dur:.2f}s ok={ok})")
                        durations.append(dur)
                        queue_waits.append(qwait)
                        return doc
                    except Exception:
                        t_end = loop.time()
                        log.exception(f"[crawl4ai#{run_id}] FAIL  { _label(i,u) } +{t_end - t0:.2f}s")
                        queue_waits.append(qwait)
                        return None
            docs = await asyncio.gather(*(_guarded(i, u) for i, u in enumerate(urls, 1)))
            docs = [d for d in docs if d and getattr(d, "metadata", None) and d.metadata.get("source")]
        
            wall = loop.time() - t0
            if durations:
                sum_dur = sum(durations)
                max_dur = max(durations)
                p95 = statistics.quantiles(durations, n=20)[-1] if len(durations) >= 2 else durations[0]
                avg_q = sum(queue_waits) / max(1, len(queue_waits))
                speedup = (sum_dur / wall) if wall > 0 else float('inf')
                log.info(
                    f"[crawl4ai#{run_id}] SUMMARY-R1 n={len(urls)} wall={wall:.2f}s "
                    f"sum_dur={sum_dur:.2f}s max_dur={max_dur:.2f}s "
                    f"p95={p95:.2f}s avg_queue_wait={avg_q:.2f}s "
                    f"speedup≈{speedup:.2f}x (concurrency={concurrency})"
                )
            else:
                log.info(f"[crawl4ai#{run_id}] SUMMARY-R1 n={len(urls)} wall={wall:.2f}s (no tasks)")

        else:
            loader = get_web_loader(urls, verify_ssl=verify_ssl, requests_per_second=rps, trust_env=trust_env)
            docs = await loader.aload()
            docs = [d for d in docs if d and getattr(d, "metadata", None) and d.metadata.get("source")]

        if not docs:
            tried = {_normalize_url(u) for u in urls}

            variant_queries = _make_variants(form_data.query, n=2)
            second_urls_all = []
            for q2 in variant_queries:
                try:
                    web_results2 = await search_web_async(
                        request, engine, q2,
                        limit=eff_limit,
                        page_size=form_data.page_size,
                        max_conc=form_data.concurrency,
                        run_id=run_id,
                    )
                    second_urls_all.extend([r.link for r in web_results2])
                except Exception as e:
                    log.warning("[search:R2#%s] requery %r failed: %s", run_id, q2, e)

            second_urls = []
            for u in second_urls_all:
                nu = _normalize_url(u)
                if nu and nu not in tried:
                    tried.add(nu)
                    second_urls.append(u)

            second_urls = dedupe_urls(second_urls, keep_per_domain=keep_per_domain)
            second_urls = second_urls[:min(top_k_fetch, eff_limit)]

            if not second_urls:
                log.info("[search:R2#%s] no new urls after requery (q=%r)", run_id, form_data.query)
                return {"status": True, "collection_name": None, "filenames": [], "loaded_count": 0, "docs": []}

            log.info("[search:R2#%s] q=%r new_urls=%d (after requery)", run_id, form_data.query, len(second_urls))

            if use_crawl4ai:
                loop2 = asyncio.get_running_loop()
                t0_2 = loop2.time()
                sem2 = asyncio.Semaphore(concurrency)

                durations2: list[float] = []
                queue_waits2: list[float] = []

                def _label2(i, u):
                    from urllib.parse import urlparse
                    try:
                        host = urlparse(u).netloc or u
                    except Exception:
                        host = u
                    return f"r2u{i}@{host}"

                async def _guarded_r2(i: int, u: str):
                    t_enq = loop2.time()
                    log.info(f"[crawl4ai#{run_id}] ENQ  { _label2(i,u) } +{t_enq - t0_2:.2f}s")

                    async with sem2:
                        t_acq = loop2.time()
                        qwait = t_acq - t_enq
                        log.info(f"[crawl4ai#{run_id}] START { _label2(i,u) } +{t_acq - t0_2:.2f}s (queue_wait={qwait:.2f}s)")
                        try:
                            doc = await _fetch_one_with_crawl4ai_fallback(
                                request=request, url=u, timeout_s=timeout_s,
                                user_agent="Open WebUI (Crawl4AI)",
                                verify_ssl=verify_ssl, rps=rps, trust_env=trust_env,
                            )
                            t_end = loop2.time()
                            dur = t_end - t_acq
                            ok = bool(doc and getattr(doc, "metadata", None) and doc.metadata.get("source"))
                            log.info(f"[crawl4ai#{run_id}] DONE  { _label2(i,u) } +{t_end - t0_2:.2f}s (dur={dur:.2f}s ok={ok})")
                            durations2.append(dur)
                            queue_waits2.append(qwait)
                            return doc
                        except Exception:
                            t_end = loop2.time()
                            log.exception(f"[crawl4ai#{run_id}] FAIL  { _label2(i,u) } +{t_end - t0_2:.2f}s")
                            queue_waits2.append(qwait)
                            return None
                        
                docs2 = await asyncio.gather(*(_guarded_r2(i, u) for i, u in enumerate(second_urls, 1)))
                docs2 = [d for d in docs2 if d and getattr(d, "metadata", None) and d.metadata.get("source")]
            
                wall2 = loop2.time() - t0_2

                if durations2:
                    sum_dur2 = sum(durations2)
                    max_dur2 = max(durations2)
                    p95_2 = statistics.quantiles(durations2, n=20)[-1] if len(durations2) >= 2 else durations2[0]
                    avg_q2 = sum(queue_waits2) / max(1, len(queue_waits2))
                    speedup2 = (sum_dur2 / wall2) if wall2 > 0 else float('inf')
                    log.info(
                        f"[crawl4ai#{run_id}] SUMMARY-R2 n={len(second_urls)} wall={wall2:.2f}s "
                        f"sum_dur={sum_dur2:.2f}s max_dur={max_dur2:.2f}s "
                        f"p95={p95_2:.2f}s avg_queue_wait={avg_q2:.2f}s "
                        f"speedup≈{speedup2:.2f}x (concurrency={concurrency})"
                    )
                else:
                    log.info(f"[crawl4ai#{run_id}] SUMMARY-R2 n={len(second_urls)} wall={wall2:.2f}s (no tasks)")

            else:
                loader2 = get_web_loader(second_urls, verify_ssl=verify_ssl, requests_per_second=rps, trust_env=trust_env)
                docs2 = await loader2.aload()
                docs2 = [d for d in docs2 if d and getattr(d, "metadata", None) and d.metadata.get("source")]

            if not docs2:
                log.info("[search:R2#%s] fetched 0 docs from %d new urls", run_id, len(second_urls))
                return {"status": True, "collection_name": None, "filenames": [], "loaded_count": 0, "docs": []}

            docs = docs2
            urls = [d.metadata["source"] for d in docs]

        if bypass:
            if len(docs) > eff_limit:
                docs = docs[:eff_limit]
            return {
                "status": True,
                "collection_name": None,
                "filenames": [d.metadata["source"] for d in docs],
                "docs": [{"content": d.page_content, "metadata": d.metadata} for d in docs],
                "loaded_count": len(docs),
            }

        enable_embed_filter = bool(getattr(cfg, "ENABLE_WEB_INLINE_EMBED_FILTER", False))
        vector_topk = int(getattr(cfg, "WEB_INLINE_VECTOR_TOPK", 0) or 30)
        encoding_name = getattr(cfg, "TIKTOKEN_ENCODING_NAME", None)
        max_doc_tokens = int(getattr(cfg, "WEB_INLINE_EMBED_MAX_TOKENS", 0) or 1200)

        rerank_candidates = docs
        if enable_embed_filter and getattr(request.app.state, "EMBEDDING_FUNCTION", None):
            try:
                qv = request.app.state.EMBEDDING_FUNCTION(form_data.query, prefix=RAG_EMBEDDING_QUERY_PREFIX, user=user)
                texts_for_embed = [
                    _trim_by_tokens(d.page_content or "", max_doc_tokens, encoding_name).replace("\n", " ")
                    for d in docs
                ]
                doc_vecs = request.app.state.EMBEDDING_FUNCTION(
                    texts_for_embed, prefix=RAG_EMBEDDING_CONTENT_PREFIX, user=user
                )
                import math
                def _cos(a, b):
                    dot = sum(x*y for x, y in zip(a, b))
                    na = math.sqrt(sum(x*x for x in a)) or 1e-9
                    nb = math.sqrt(sum(x*x for x in b)) or 1e-9
                    return dot/(na*nb)
                scored = [(i, _cos(qv, dv)) for i, dv in enumerate(doc_vecs)]
                scored.sort(key=lambda x: x[1], reverse=True)
                keep_idx = [i for i, _ in scored[:min(vector_topk, len(scored))]]
                rerank_candidates = [docs[i] for i in keep_idx]
            except Exception as _e:
                log.warning("embed-filter failed, fallback no-filter: %s", _e)
                rerank_candidates = docs

        enable_inline_rerank = bool(getattr(cfg, "ENABLE_WEB_INLINE_RERANK", False))
        rerank_topn = int(getattr(cfg, "WEB_INLINE_RERANK_TOPN", 0) or 10)
        rf = getattr(request.app.state, "rf", None)

        final_docs = rerank_candidates
        if enable_inline_rerank and rf is not None:
            pairs = [(form_data.query, _trim_by_tokens(d.page_content or "", max_doc_tokens, encoding_name))
                     for d in rerank_candidates]
            def _score_sync():
                try: return list(rf.predict(pairs))
                except Exception: return list(rf.score(pairs))
            scores = await run_in_threadpool(_score_sync)
            order = sorted(range(len(rerank_candidates)), key=lambda i: scores[i], reverse=True)
            final_docs = [rerank_candidates[i] for i in order[:min(rerank_topn, len(order))]]

        if len(final_docs) > eff_limit:
            final_docs = final_docs[:eff_limit]
        urls_final = [d.metadata["source"] for d in final_docs]
        collection_names = []
        for i, doc in enumerate(final_docs):
            if not doc or not doc.page_content:
                continue
            cname = f"web-search-{calculate_sha256_string(form_data.query + '-' + urls_final[i])}"[:63]
            collection_names.append(cname)
            await run_in_threadpool(save_docs_to_vector_db, request, [doc], cname, overwrite=True, user=user)

        return {"status": True, "collection_names": collection_names, "filenames": urls_final, "loaded_count": len(final_docs)}
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT(e))


class QueryDocForm(BaseModel):
    collection_name: str
    query: str
    k: Optional[int] = None
    k_reranker: Optional[int] = None
    r: Optional[float] = None
    hybrid: Optional[bool] = None


@router.post("/query/doc")
def query_doc_handler(
    request: Request,
    form_data: QueryDocForm,
    user=Depends(get_verified_user),
):
    try:
        if request.app.state.config.ENABLE_RAG_HYBRID_SEARCH:
            collection_results = {}
            collection_results[form_data.collection_name] = VECTOR_DB_CLIENT.get(
                collection_name=form_data.collection_name
            )
            return query_doc_with_hybrid_search(
                collection_name=form_data.collection_name,
                collection_result=collection_results[form_data.collection_name],
                query=form_data.query,
                embedding_function=lambda query, prefix: request.app.state.EMBEDDING_FUNCTION(
                    query, prefix=prefix, user=user
                ),
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
                reranking_function=request.app.state.rf,
                k_reranker=form_data.k_reranker
                or request.app.state.config.TOP_K_RERANKER,
                r=(
                    form_data.r
                    if form_data.r
                    else request.app.state.config.RELEVANCE_THRESHOLD
                ),
                user=user,
            )
        else:
            return query_doc(
                collection_name=form_data.collection_name,
                query_embedding=request.app.state.EMBEDDING_FUNCTION(
                    form_data.query, prefix=RAG_EMBEDDING_QUERY_PREFIX, user=user
                ),
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
                user=user,
            )
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


class QueryCollectionsForm(BaseModel):
    collection_names: list[str]
    query: str
    k: Optional[int] = None
    k_reranker: Optional[int] = None
    r: Optional[float] = None
    hybrid: Optional[bool] = None


@router.post("/query/collection")
def query_collection_handler(
    request: Request,
    form_data: QueryCollectionsForm,
    user=Depends(get_verified_user),
):
    try:
        if request.app.state.config.ENABLE_RAG_HYBRID_SEARCH:
            return query_collection_with_hybrid_search(
                collection_names=form_data.collection_names,
                queries=[form_data.query],
                embedding_function=lambda query, prefix: request.app.state.EMBEDDING_FUNCTION(
                    query, prefix=prefix, user=user
                ),
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
                reranking_function=request.app.state.rf,
                k_reranker=form_data.k_reranker
                or request.app.state.config.TOP_K_RERANKER,
                r=(
                    form_data.r
                    if form_data.r
                    else request.app.state.config.RELEVANCE_THRESHOLD
                ),
            )
        else:
            return query_collection(
                collection_names=form_data.collection_names,
                queries=[form_data.query],
                embedding_function=lambda query, prefix: request.app.state.EMBEDDING_FUNCTION(
                    query, prefix=prefix, user=user
                ),
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
            )

    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


####################################
#
# Vector DB operations
#
####################################


class DeleteForm(BaseModel):
    collection_name: str
    file_id: str


@router.post("/delete")
def delete_entries_from_collection(form_data: DeleteForm, user=Depends(get_admin_user)):
    try:
        if VECTOR_DB_CLIENT.has_collection(collection_name=form_data.collection_name):
            file = Files.get_file_by_id(form_data.file_id)
            hash = file.hash

            VECTOR_DB_CLIENT.delete(
                collection_name=form_data.collection_name,
                metadata={"hash": hash},
            )
            return {"status": True}
        else:
            return {"status": False}
    except Exception as e:
        log.exception(e)
        return {"status": False}


@router.post("/reset/db")
def reset_vector_db(user=Depends(get_admin_user)):
    VECTOR_DB_CLIENT.reset()
    Knowledges.delete_all_knowledge()


@router.post("/reset/uploads")
def reset_upload_dir(user=Depends(get_admin_user)) -> bool:
    folder = f"{UPLOAD_DIR}"
    try:
        # Check if the directory exists
        if os.path.exists(folder):
            # Iterate over all the files and directories in the specified directory
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # Remove the file or link
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # Remove the directory
                except Exception as e:
                    log.exception(f"Failed to delete {file_path}. Reason: {e}")
        else:
            log.warning(f"The directory {folder} does not exist")
    except Exception as e:
        log.exception(f"Failed to process the directory {folder}. Reason: {e}")
    return True


if ENV == "dev":

    @router.get("/ef/{text}")
    async def get_embeddings(request: Request, text: Optional[str] = "Hello World!"):
        return {
            "result": request.app.state.EMBEDDING_FUNCTION(
                text, prefix=RAG_EMBEDDING_QUERY_PREFIX
            )
        }


class BatchProcessFilesForm(BaseModel):
    files: List[FileModel]
    collection_name: str


class BatchProcessFilesResult(BaseModel):
    file_id: str
    status: str
    error: Optional[str] = None


class BatchProcessFilesResponse(BaseModel):
    results: List[BatchProcessFilesResult]
    errors: List[BatchProcessFilesResult]


@router.post("/process/files/batch")
def process_files_batch(
    request: Request,
    form_data: BatchProcessFilesForm,
    user=Depends(get_verified_user),
) -> BatchProcessFilesResponse:
    """
    Process a batch of files and save them to the vector database.
    """
    results: List[BatchProcessFilesResult] = []
    errors: List[BatchProcessFilesResult] = []
    collection_name = form_data.collection_name

    # Prepare all documents first
    all_docs: List[Document] = []
    for file in form_data.files:
        try:
            text_content = file.data.get("content", "")

            docs: List[Document] = [
                Document(
                    page_content=text_content.replace("<br/>", "\n"),
                    metadata={
                        **file.meta,
                        "name": file.filename,
                        "created_by": file.user_id,
                        "file_id": file.id,
                        "source": file.filename,
                    },
                )
            ]

            hash = calculate_sha256_string(text_content)
            Files.update_file_hash_by_id(file.id, hash)
            Files.update_file_data_by_id(file.id, {"content": text_content})

            all_docs.extend(docs)
            results.append(BatchProcessFilesResult(file_id=file.id, status="prepared"))

        except Exception as e:
            log.error(f"process_files_batch: Error processing file {file.id}: {str(e)}")
            errors.append(
                BatchProcessFilesResult(file_id=file.id, status="failed", error=str(e))
            )

    # Save all documents in one batch
    if all_docs:
        try:
            save_docs_to_vector_db(
                request=request,
                docs=all_docs,
                collection_name=collection_name,
                add=True,
                user=user,
            )

            # Update all files with collection name
            for result in results:
                Files.update_file_metadata_by_id(
                    result.file_id, {"collection_name": collection_name}
                )
                result.status = "completed"

        except Exception as e:
            log.error(
                f"process_files_batch: Error saving documents to vector DB: {str(e)}"
            )
            for result in results:
                result.status = "failed"
                errors.append(
                    BatchProcessFilesResult(file_id=result.file_id, error=str(e))
                )

    return BatchProcessFilesResponse(results=results, errors=errors)
