import asyncio
import logging
import socket
import ssl
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, time, timedelta
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from typing import Any, Dict
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Union,
    Literal,
)
import aiohttp
import certifi
import validators
from langchain_community.document_loaders import PlaywrightURLLoader, WebBaseLoader
from langchain_community.document_loaders.firecrawl import FireCrawlLoader
from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document
from open_webui.retrieval.loaders.tavily import TavilyLoader
from open_webui.constants import ERROR_MESSAGES
from open_webui.config import (
    ENABLE_RAG_LOCAL_WEB_FETCH,
    PLAYWRIGHT_WS_URL,
    PLAYWRIGHT_TIMEOUT,
    WEB_LOADER_ENGINE,
    FIRECRAWL_API_BASE_URL,
    FIRECRAWL_API_KEY,
    TAVILY_API_KEY,
    TAVILY_EXTRACT_DEPTH,
)
from open_webui.env import SRC_LOG_LEVELS

import os
from inspect import signature
from fastapi import Request
from crawl4ai.async_configs import CrawlerRunConfig 


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])


def validate_url(url: Union[str, Sequence[str]]):
    if isinstance(url, str):
        if isinstance(validators.url(url), validators.ValidationError):
            raise ValueError(ERROR_MESSAGES.INVALID_URL)
        if not ENABLE_RAG_LOCAL_WEB_FETCH:
            # Local web fetch is disabled, filter out any URLs that resolve to private IP addresses
            parsed_url = urllib.parse.urlparse(url)
            # Get IPv4 and IPv6 addresses
            ipv4_addresses, ipv6_addresses = resolve_hostname(parsed_url.hostname)
            # Check if any of the resolved addresses are private
            # This is technically still vulnerable to DNS rebinding attacks, as we don't control WebBaseLoader
            for ip in ipv4_addresses:
                if validators.ipv4(ip, private=True):
                    raise ValueError(ERROR_MESSAGES.INVALID_URL)
            for ip in ipv6_addresses:
                if validators.ipv6(ip, private=True):
                    raise ValueError(ERROR_MESSAGES.INVALID_URL)
        return True
    elif isinstance(url, Sequence):
        return all(validate_url(u) for u in url)
    else:
        return False


def safe_validate_urls(url: Sequence[str]) -> Sequence[str]:
    valid_urls = []
    for u in url:
        try:
            if validate_url(u):
                valid_urls.append(u)
        except ValueError:
            continue
    return valid_urls


def resolve_hostname(hostname):
    # Get address information
    addr_info = socket.getaddrinfo(hostname, None)

    # Extract IP addresses from address information
    ipv4_addresses = [info[4][0] for info in addr_info if info[0] == socket.AF_INET]
    ipv6_addresses = [info[4][0] for info in addr_info if info[0] == socket.AF_INET6]

    return ipv4_addresses, ipv6_addresses


def extract_metadata(soup, url):
    metadata = {"source": url}
    if title := soup.find("title"):
        metadata["title"] = title.get_text()
    if description := soup.find("meta", attrs={"name": "description"}):
        metadata["description"] = description.get("content", "No description found.")
    if html := soup.find("html"):
        metadata["language"] = html.get("lang", "No language found.")
    return metadata


def verify_ssl_cert(url: str) -> bool:
    """Verify SSL certificate for the given URL."""
    if not url.startswith("https://"):
        return True

    try:
        hostname = url.split("://")[-1].split("/")[0]
        context = ssl.create_default_context(cafile=certifi.where())
        with context.wrap_socket(ssl.socket(), server_hostname=hostname) as s:
            s.connect((hostname, 443))
        return True
    except ssl.SSLError:
        return False
    except Exception as e:
        log.warning(f"SSL verification failed for {url}: {str(e)}")
        return False


class RateLimitMixin:
    async def _wait_for_rate_limit(self):
        """Wait to respect the rate limit if specified."""
        if self.requests_per_second and self.last_request_time:
            min_interval = timedelta(seconds=1.0 / self.requests_per_second)
            time_since_last = datetime.now() - self.last_request_time
            if time_since_last < min_interval:
                await asyncio.sleep((min_interval - time_since_last).total_seconds())
        self.last_request_time = datetime.now()

    def _sync_wait_for_rate_limit(self):
        """Synchronous version of rate limit wait."""
        if self.requests_per_second and self.last_request_time:
            min_interval = timedelta(seconds=1.0 / self.requests_per_second)
            time_since_last = datetime.now() - self.last_request_time
            if time_since_last < min_interval:
                time.sleep((min_interval - time_since_last).total_seconds())
        self.last_request_time = datetime.now()


class URLProcessingMixin:
    def _verify_ssl_cert(self, url: str) -> bool:
        """Verify SSL certificate for a URL."""
        return verify_ssl_cert(url)

    async def _safe_process_url(self, url: str) -> bool:
        """Perform safety checks before processing a URL."""
        if self.verify_ssl and not self._verify_ssl_cert(url):
            raise ValueError(f"SSL certificate verification failed for {url}")
        await self._wait_for_rate_limit()
        return True

    def _safe_process_url_sync(self, url: str) -> bool:
        """Synchronous version of safety checks."""
        if self.verify_ssl and not self._verify_ssl_cert(url):
            raise ValueError(f"SSL certificate verification failed for {url}")
        self._sync_wait_for_rate_limit()
        return True


class SafeFireCrawlLoader(BaseLoader, RateLimitMixin, URLProcessingMixin):
    def __init__(
        self,
        web_paths,
        verify_ssl: bool = True,
        trust_env: bool = False,
        requests_per_second: Optional[float] = None,
        continue_on_failure: bool = True,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        mode: Literal["crawl", "scrape", "map"] = "crawl",
        proxy: Optional[Dict[str, str]] = None,
        params: Optional[Dict] = None,
    ):
        """Concurrent document loader for FireCrawl operations.

        Executes multiple FireCrawlLoader instances concurrently using thread pooling
        to improve bulk processing efficiency.
        Args:
            web_paths: List of URLs/paths to process.
            verify_ssl: If True, verify SSL certificates.
            trust_env: If True, use proxy settings from environment variables.
            requests_per_second: Number of requests per second to limit to.
            continue_on_failure (bool): If True, continue loading other URLs on failure.
            api_key: API key for FireCrawl service. Defaults to None
                (uses FIRE_CRAWL_API_KEY environment variable if not provided).
            api_url: Base URL for FireCrawl API. Defaults to official API endpoint.
            mode: Operation mode selection:
                - 'crawl': Website crawling mode (default)
                - 'scrape': Direct page scraping
                - 'map': Site map generation
            proxy: Proxy override settings for the FireCrawl API.
            params: The parameters to pass to the Firecrawl API.
                Examples include crawlerOptions.
                For more details, visit: https://github.com/mendableai/firecrawl-py
        """
        proxy_server = proxy.get("server") if proxy else None
        if trust_env and not proxy_server:
            env_proxies = urllib.request.getproxies()
            env_proxy_server = env_proxies.get("https") or env_proxies.get("http")
            if env_proxy_server:
                if proxy:
                    proxy["server"] = env_proxy_server
                else:
                    proxy = {"server": env_proxy_server}
        self.web_paths = web_paths
        self.verify_ssl = verify_ssl
        self.requests_per_second = requests_per_second
        self.last_request_time = None
        self.trust_env = trust_env
        self.continue_on_failure = continue_on_failure
        self.api_key = api_key
        self.api_url = api_url
        self.mode = mode
        self.params = params

    def lazy_load(self) -> Iterator[Document]:
        """Load documents concurrently using FireCrawl."""
        for url in self.web_paths:
            try:
                self._safe_process_url_sync(url)
                loader = FireCrawlLoader(
                    url=url,
                    api_key=self.api_key,
                    api_url=self.api_url,
                    mode=self.mode,
                    params=self.params,
                )
                yield from loader.lazy_load()
            except Exception as e:
                if self.continue_on_failure:
                    log.exception(f"Error loading {url}: {e}")
                    continue
                raise e

    async def alazy_load(self):
        """Async version of lazy_load."""
        for url in self.web_paths:
            try:
                await self._safe_process_url(url)
                loader = FireCrawlLoader(
                    url=url,
                    api_key=self.api_key,
                    api_url=self.api_url,
                    mode=self.mode,
                    params=self.params,
                )
                async for document in loader.alazy_load():
                    yield document
            except Exception as e:
                if self.continue_on_failure:
                    log.exception(f"Error loading {url}: {e}")
                    continue
                raise e


class SafeTavilyLoader(BaseLoader, RateLimitMixin, URLProcessingMixin):
    def __init__(
        self,
        web_paths: Union[str, List[str]],
        api_key: str,
        extract_depth: Literal["basic", "advanced"] = "basic",
        continue_on_failure: bool = True,
        requests_per_second: Optional[float] = None,
        verify_ssl: bool = True,
        trust_env: bool = False,
        proxy: Optional[Dict[str, str]] = None,
    ):
        """Initialize SafeTavilyLoader with rate limiting and SSL verification support.

        Args:
            web_paths: List of URLs/paths to process.
            api_key: The Tavily API key.
            extract_depth: Depth of extraction ("basic" or "advanced").
            continue_on_failure: Whether to continue if extraction of a URL fails.
            requests_per_second: Number of requests per second to limit to.
            verify_ssl: If True, verify SSL certificates.
            trust_env: If True, use proxy settings from environment variables.
            proxy: Optional proxy configuration.
        """
        # Initialize proxy configuration if using environment variables
        proxy_server = proxy.get("server") if proxy else None
        if trust_env and not proxy_server:
            env_proxies = urllib.request.getproxies()
            env_proxy_server = env_proxies.get("https") or env_proxies.get("http")
            if env_proxy_server:
                if proxy:
                    proxy["server"] = env_proxy_server
                else:
                    proxy = {"server": env_proxy_server}

        # Store parameters for creating TavilyLoader instances
        self.web_paths = web_paths if isinstance(web_paths, list) else [web_paths]
        self.api_key = api_key
        self.extract_depth = extract_depth
        self.continue_on_failure = continue_on_failure
        self.verify_ssl = verify_ssl
        self.trust_env = trust_env
        self.proxy = proxy

        # Add rate limiting
        self.requests_per_second = requests_per_second
        self.last_request_time = None

    def lazy_load(self) -> Iterator[Document]:
        """Load documents with rate limiting support, delegating to TavilyLoader."""
        valid_urls = []
        for url in self.web_paths:
            try:
                self._safe_process_url_sync(url)
                valid_urls.append(url)
            except Exception as e:
                log.warning(f"SSL verification failed for {url}: {str(e)}")
                if not self.continue_on_failure:
                    raise e
        if not valid_urls:
            if self.continue_on_failure:
                log.warning("No valid URLs to process after SSL verification")
                return
            raise ValueError("No valid URLs to process after SSL verification")
        try:
            loader = TavilyLoader(
                urls=valid_urls,
                api_key=self.api_key,
                extract_depth=self.extract_depth,
                continue_on_failure=self.continue_on_failure,
            )
            yield from loader.lazy_load()
        except Exception as e:
            if self.continue_on_failure:
                log.exception(f"Error extracting content from URLs: {e}")
            else:
                raise e

    async def alazy_load(self) -> AsyncIterator[Document]:
        """Async version with rate limiting and SSL verification."""
        valid_urls = []
        for url in self.web_paths:
            try:
                await self._safe_process_url(url)
                valid_urls.append(url)
            except Exception as e:
                log.warning(f"SSL verification failed for {url}: {str(e)}")
                if not self.continue_on_failure:
                    raise e

        if not valid_urls:
            if self.continue_on_failure:
                log.warning("No valid URLs to process after SSL verification")
                return
            raise ValueError("No valid URLs to process after SSL verification")

        try:
            loader = TavilyLoader(
                urls=valid_urls,
                api_key=self.api_key,
                extract_depth=self.extract_depth,
                continue_on_failure=self.continue_on_failure,
            )
            async for document in loader.alazy_load():
                yield document
        except Exception as e:
            if self.continue_on_failure:
                log.exception(f"Error loading URLs: {e}")
            else:
                raise e


class SafePlaywrightURLLoader(PlaywrightURLLoader, RateLimitMixin, URLProcessingMixin):
    """Load HTML pages safely with Playwright, supporting SSL verification, rate limiting, and remote browser connection.

    Attributes:
        web_paths (List[str]): List of URLs to load.
        verify_ssl (bool): If True, verify SSL certificates.
        trust_env (bool): If True, use proxy settings from environment variables.
        requests_per_second (Optional[float]): Number of requests per second to limit to.
        continue_on_failure (bool): If True, continue loading other URLs on failure.
        headless (bool): If True, the browser will run in headless mode.
        proxy (dict): Proxy override settings for the Playwright session.
        playwright_ws_url (Optional[str]): WebSocket endpoint URI for remote browser connection.
        playwright_timeout (Optional[int]): Maximum operation time in milliseconds.
    """

    def __init__(
        self,
        web_paths: List[str],
        verify_ssl: bool = True,
        trust_env: bool = False,
        requests_per_second: Optional[float] = None,
        continue_on_failure: bool = True,
        headless: bool = True,
        remove_selectors: Optional[List[str]] = None,
        proxy: Optional[Dict[str, str]] = None,
        playwright_ws_url: Optional[str] = None,
        playwright_timeout: Optional[int] = 10000,
    ):
        """Initialize with additional safety parameters and remote browser support."""

        proxy_server = proxy.get("server") if proxy else None
        if trust_env and not proxy_server:
            env_proxies = urllib.request.getproxies()
            env_proxy_server = env_proxies.get("https") or env_proxies.get("http")
            if env_proxy_server:
                if proxy:
                    proxy["server"] = env_proxy_server
                else:
                    proxy = {"server": env_proxy_server}

        # We'll set headless to False if using playwright_ws_url since it's handled by the remote browser
        super().__init__(
            urls=web_paths,
            continue_on_failure=continue_on_failure,
            headless=headless if playwright_ws_url is None else False,
            remove_selectors=remove_selectors,
            proxy=proxy,
        )
        self.verify_ssl = verify_ssl
        self.requests_per_second = requests_per_second
        self.last_request_time = None
        self.playwright_ws_url = playwright_ws_url
        self.trust_env = trust_env
        self.playwright_timeout = playwright_timeout

    def lazy_load(self) -> Iterator[Document]:
        """Safely load URLs synchronously with support for remote browser."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Use remote browser if ws_endpoint is provided, otherwise use local browser
            if self.playwright_ws_url:
                browser = p.chromium.connect(self.playwright_ws_url)
            else:
                browser = p.chromium.launch(headless=self.headless, proxy=self.proxy)

            for url in self.urls:
                try:
                    self._safe_process_url_sync(url)
                    page = browser.new_page()
                    response = page.goto(url, timeout=self.playwright_timeout)
                    if response is None:
                        raise ValueError(f"page.goto() returned None for url {url}")

                    text = self.evaluator.evaluate(page, browser, response)
                    metadata = {"source": url}
                    yield Document(page_content=text, metadata=metadata)
                except Exception as e:
                    if self.continue_on_failure:
                        log.exception(f"Error loading {url}: {e}")
                        continue
                    raise e
            browser.close()

    async def alazy_load(self) -> AsyncIterator[Document]:
        """Safely load URLs asynchronously with support for remote browser."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Use remote browser if ws_endpoint is provided, otherwise use local browser
            if self.playwright_ws_url:
                browser = await p.chromium.connect(self.playwright_ws_url)
            else:
                browser = await p.chromium.launch(
                    headless=self.headless, proxy=self.proxy
                )

            for url in self.urls:
                try:
                    await self._safe_process_url(url)
                    page = await browser.new_page()
                    response = await page.goto(url, timeout=self.playwright_timeout)
                    if response is None:
                        raise ValueError(f"page.goto() returned None for url {url}")

                    text = await self.evaluator.evaluate_async(page, browser, response)
                    metadata = {"source": url}
                    yield Document(page_content=text, metadata=metadata)
                except Exception as e:
                    if self.continue_on_failure:
                        log.exception(f"Error loading {url}: {e}")
                        continue
                    raise e
            await browser.close()


class SafeWebBaseLoader(WebBaseLoader):
    """WebBaseLoader with enhanced error handling for URLs."""

    def __init__(self, trust_env: bool = False, *args, **kwargs):
        """Initialize SafeWebBaseLoader
        Args:
            trust_env (bool, optional): set to True if using proxy to make web requests, for example
                using http(s)_proxy environment variables. Defaults to False.
        """
        super().__init__(*args, **kwargs)
        self.trust_env = trust_env

    async def _fetch(
        self, url: str, retries: int = 3, cooldown: int = 2, backoff: float = 1.5
    ) -> str:
        async with aiohttp.ClientSession(trust_env=self.trust_env) as session:
            for i in range(retries):
                try:
                    kwargs: Dict = dict(
                        headers=self.session.headers,
                        cookies=self.session.cookies.get_dict(),
                    )
                    if not self.session.verify:
                        kwargs["ssl"] = False

                    async with session.get(
                        url, **(self.requests_kwargs | kwargs)
                    ) as response:
                        if self.raise_for_status:
                            response.raise_for_status()
                        return await response.text()
                except aiohttp.ClientConnectionError as e:
                    if i == retries - 1:
                        raise
                    else:
                        log.warning(
                            f"Error fetching {url} with attempt "
                            f"{i + 1}/{retries}: {e}. Retrying..."
                        )
                        await asyncio.sleep(cooldown * backoff**i)
        raise ValueError("retry count exceeded")

    def _unpack_fetch_results(
        self, results: Any, urls: List[str], parser: Union[str, None] = None
    ) -> List[Any]:
        """Unpack fetch results into BeautifulSoup objects."""
        from bs4 import BeautifulSoup

        final_results = []
        for i, result in enumerate(results):
            url = urls[i]
            if parser is None:
                if url.endswith(".xml"):
                    parser = "xml"
                else:
                    parser = self.default_parser
                self._check_parser(parser)
            final_results.append(BeautifulSoup(result, parser, **self.bs_kwargs))
        return final_results

    async def ascrape_all(
        self, urls: List[str], parser: Union[str, None] = None
    ) -> List[Any]:
        """Async fetch all urls, then return soups for all results."""
        results = await self.fetch_all(urls)
        return self._unpack_fetch_results(results, urls, parser=parser)

    def lazy_load(self) -> Iterator[Document]:
        """Lazy load text from the url(s) in web_path with error handling."""
        for path in self.web_paths:
            try:
                soup = self._scrape(path, bs_kwargs=self.bs_kwargs)
                text = soup.get_text(**self.bs_get_text_kwargs)

                # Build metadata
                metadata = extract_metadata(soup, path)

                yield Document(page_content=text, metadata=metadata)
            except Exception as e:
                # Log the error and continue with the next URL
                log.exception(f"Error loading {path}: {e}")

    async def alazy_load(self) -> AsyncIterator[Document]:
        """Async lazy load text from the url(s) in web_path."""
        results = await self.ascrape_all(self.web_paths)
        for path, soup in zip(self.web_paths, results):
            text = soup.get_text(**self.bs_get_text_kwargs)
            metadata = {"source": path}
            if title := soup.find("title"):
                metadata["title"] = title.get_text()
            if description := soup.find("meta", attrs={"name": "description"}):
                metadata["description"] = description.get(
                    "content", "No description found."
                )
            if html := soup.find("html"):
                metadata["language"] = html.get("lang", "No language found.")
            yield Document(page_content=text, metadata=metadata)

    async def aload(self) -> list[Document]:
        """Load data into Document objects."""
        return [document async for document in self.alazy_load()]


def get_web_loader(
    urls: Union[str, Sequence[str]],
    verify_ssl: bool = True,
    requests_per_second: int = 2,
    trust_env: bool = False,
):
    # Check if the URLs are valid
    safe_urls = safe_validate_urls([urls] if isinstance(urls, str) else urls)

    web_loader_args = {
        "web_paths": safe_urls,
        "verify_ssl": verify_ssl,
        "requests_per_second": requests_per_second,
        "continue_on_failure": True,
        "trust_env": trust_env,
    }

    if WEB_LOADER_ENGINE.value == "" or WEB_LOADER_ENGINE.value == "safe_web":
        WebLoaderClass = SafeWebBaseLoader
    if WEB_LOADER_ENGINE.value == "playwright":
        WebLoaderClass = SafePlaywrightURLLoader
        web_loader_args["playwright_timeout"] = PLAYWRIGHT_TIMEOUT.value * 1000
        if PLAYWRIGHT_WS_URL.value:
            web_loader_args["playwright_ws_url"] = PLAYWRIGHT_WS_URL.value

    if WEB_LOADER_ENGINE.value == "firecrawl":
        WebLoaderClass = SafeFireCrawlLoader
        web_loader_args["api_key"] = FIRECRAWL_API_KEY.value
        web_loader_args["api_url"] = FIRECRAWL_API_BASE_URL.value

    if WEB_LOADER_ENGINE.value == "tavily":
        WebLoaderClass = SafeTavilyLoader
        web_loader_args["api_key"] = TAVILY_API_KEY.value
        web_loader_args["extract_depth"] = TAVILY_EXTRACT_DEPTH.value

    if WebLoaderClass:
        web_loader = WebLoaderClass(**web_loader_args)

        log.debug(
            "Using WEB_LOADER_ENGINE %s for %s URLs",
            web_loader.__class__.__name__,
            len(safe_urls),
        )

        return web_loader
    else:
        raise ValueError(
            f"Invalid WEB_LOADER_ENGINE: {WEB_LOADER_ENGINE.value}. "
            "Please set it to 'safe_web', 'playwright', 'firecrawl', or 'tavily'."
        )


def _best_main_block(soup):
    cands = soup.select(
        "article, main, [role=main], div[itemprop='articleBody'], "
        "section[itemprop='articleBody'], .article, .Article, .story, .Story"
    ) or [soup.body]
    best = max(cands, key=lambda el: len(el.get_text(" ", strip=True)) if el else 0)
    return best

def _strip_nav_lines(md: str) -> str:
    if not md:
        return md
    out = []
    for ln in md.splitlines():
        s = ln.strip()
        if not s:
            continue
        low = s.lower()

        if low.startswith("skip to main content"):
            continue
        if s.startswith("* ") and "](" in s: 
            continue
        if s.count("](") >= 2 and len(s) <= 200:
            continue
        if "Log in" in s or "Cancel" in s:
            continue
        out.append(ln)
    return "\n".join(out)

def rule_structured_from(res, url: str) -> dict:
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse
    import json, re
    html = getattr(res, "html", "") or ""
    raw_text = (getattr(res, "markdown", None) or getattr(res, "cleaned_text", None) or "") or ""
    meta0 = getattr(res, "metadata", {}) or {}

    title = meta0.get("title") or ""
    author = None
    published_at = None

    main_text = raw_text
    if html:
        soup = BeautifulSoup(html, "html.parser")

        for sel in [
            "header","nav","footer","aside",".site-header",".header",".top-nav",
            ".global-nav",".main-nav",".breadcrumbs",".breadcrumb",".share",".social",
            ".subscribe",".newsletter",".promo",".cookie",".consent",".ad",".ads",
            ".advertisement",".sponsored",".related",".recommend",".sidebar",
            ".search",".menu",".skip-link"
        ]:
            for el in soup.select(sel):
                el.decompose()
        main = _best_main_block(soup)
        if main:
            main_text = main.get_text("\n", strip=True)
        def pick_meta(*names):
            for n in names:
                tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
                if tag and tag.get("content"):
                    return tag["content"]
        title = title or pick_meta("og:title","twitter:title")
        author = author or pick_meta("author","article:author","twitter:creator")
        date_str = pick_meta("article:published_time","og:published_time","date","pubdate")

        if not date_str:
            for sc in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(sc.string or "")
                    if isinstance(data, dict):
                        title = title or data.get("headline")
                        date_str = date_str or data.get("datePublished") or data.get("dateModified")
                        a = data.get("author")
                        if isinstance(a, dict) and not author:
                            author = a.get("name")
                        break
                except Exception:
                    pass

        if date_str:
            try:
                from dateutil import parser as dp
                published_at = dp.parse(date_str).isoformat()
            except Exception:
                pass

    main_text = _strip_nav_lines(main_text)

    summary = ""
    if main_text:
        parts = re.split(r'(?<=[。！？.!?])\s+', main_text.strip())
        summary = " ".join(parts[:3])[:400]

    from urllib.parse import urlparse
    return {
        "title": title or url,
        "published_at": published_at,
        "author": author,
        "source": urlparse(url).netloc,
        "summary": summary or None,
        "main_text": main_text or None,
        "language": None,
    }

def non_llm_extraction_strategy():
    try:
        from crawl4ai.extraction_strategy import NoExtractionStrategy
        return NoExtractionStrategy()
    except Exception:
        return None


DEFAULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title":        {"type": "string", "description": "Page/article title if available"},
        "published_at": {"type": "string", "description": "Publication date/time in ISO-8601 if found"},
        "author":       {"type": "string"},
        "source":       {"type": "string", "description": "Domain or site name"},
        "summary":      {"type": "string", "description": "Concise 3–5 sentence summary"},
        "main_text":    {"type": "string", "description": "Clean main content/body text"},
        "language":     {"type": "string"},
        "top_quotes":   {"type": "array", "items": {"type": "string"}, "maxItems": 5}
    },
    "required": ["title", "summary"]
}

def _mk_run_cfg(**kwargs) -> CrawlerRunConfig:

    try:
        params = signature(CrawlerRunConfig).parameters
        allowed = {k: v for k, v in kwargs.items() if k in params}
        if not allowed:
            log.warning("[crawl4ai] no matching args for CrawlerRunConfig, keys=%s", list(kwargs.keys()))
        return CrawlerRunConfig(**allowed)
    except Exception as ex:
        log.error("[crawl4ai] building CrawlerRunConfig failed: %s", ex)
        return CrawlerRunConfig()

def _mk_extraction_strategy(schema: Dict[str, Any]):

    try:
        from crawl4ai.extraction_strategy import LLMExtractionStrategy, NoExtractionStrategy
    except Exception as ex:
        log.warning("[crawl4ai] extraction module not available: %s; will not pass extraction_strategy", ex)
        return None 

    model = os.getenv("CRAWL4AI_LLM_MODEL", "gpt-4o-mini")

    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        try:
            return LLMExtractionStrategy(
                model=model,
                api_key=api_key,
                schema=schema,
                temperature=0,

            )
        except Exception as ex:
            log.warning("[crawl4ai] LLMExtractionStrategy init failed, fallback to NoExtractionStrategy: %s", ex)


    try:
        return NoExtractionStrategy()
    except Exception:
        log.warning("[crawl4ai] NoExtractionStrategy not available; will not pass extraction_strategy")
        return None


def _pick_structured_payload(res) -> Dict[str, Any]:

    for key in ("extracted_content", "extracted_data", "extraction", "structured_data", "json"):
        data = getattr(res, key, None)
        if isinstance(data, dict) and data:
            return data

    for key in ("markdown_json", "text_json"):
        data = getattr(res, key, None)
        if isinstance(data, dict) and data:
            return data
    return {}


def _pick_text(res) -> str:

    for key in ("markdown", "cleaned_text", "text", "html"):
        v = getattr(res, key, None)
        if isinstance(v, str) and v.strip():
            return v
    return ""

async def _crawl4ai_fetch_docs(
    request: Request,
    urls: list[str],
    *,
    timeout_sec: float = 15.0,
    concurrency: int = 3,
    user_agent: str = "Open WebUI / Crawl4AI",
    schema: Optional[Dict[str, Any]] = None,
) -> list[Document]:

    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode

    cfg = getattr(request.app.state, "config", None)
    if cfg:
        concurrency = int(getattr(cfg, "WEB_SEARCH_CONCURRENT_REQUESTS", concurrency) or concurrency)

        pw_ms = getattr(cfg, "PLAYWRIGHT_TIMEOUT", None)
        if pw_ms:
            try:
                timeout_sec = max(timeout_sec, float(pw_ms) / 1000.0)
            except Exception:
                pass

    urls = [u for u in dict.fromkeys(urls) if u]
    if not urls:
        return []

    bcfg = BrowserConfig(
        headless=True,
        user_agent=user_agent,
    )

    strategy = _mk_extraction_strategy(schema or DEFAULT_SCHEMA)

    kwargs = dict(
        cache_mode=CacheMode.BYPASS,
        js=True,
        js_render=True,
        js_timeout=10,
        browser_type="chromium",
        max_tasks=concurrency,
        timeout=int(timeout_sec * 1000),
        remove_overlay=True,
    )
    kwargs.update({
        "remove_selectors": [
            "header","nav","footer","aside",".site-header",".header",".top-nav",
            ".global-nav",".main-nav",".breadcrumbs",".breadcrumb",".share",".social",
            ".subscribe",".newsletter",".promo",".cookie",".consent",".ad",".ads",
            ".advertisement",".sponsored",".related",".recommend",".sidebar",
            ".search",".menu",".skip-link"
        ],
        "readability": True, 
    })


    if strategy is not None:
        kwargs["extraction_strategy"] = strategy

    run_cfg = _mk_run_cfg(**kwargs)

    sem = asyncio.Semaphore(max(1, concurrency))
    docs: list[Document] = []

    loop = asyncio.get_running_loop()
    t0 = loop.time()

    async with AsyncWebCrawler(config=bcfg) as crawler:
        async def _one(u: str):
            async with sem:

                start = loop.time()
                log.info(f"[crawl4ai] start {u} | Concurrent crawling started")
                try:
                
                    res = await crawler.arun(url=u, config=run_cfg)

                    structured = _pick_structured_payload(res)

                    if not structured:
                        structured = rule_structured_from(res, u)

                    page_text = (structured.get("main_text") or structured.get("summary") or "").strip()
                    if not page_text:
                        page_text = _pick_text(res)

                    docs.append(Document(
                        page_content=page_text,
                        metadata={
                            "source": u,
                            "title": structured.get("title") or u,
                            "loader": "crawl4ai",
                            "structured": structured, 
                        }
                    ))

                    # log.info(f"[crawl4ai] done {u} in {loop.time() - start:.2f}s | Time per page")

                except Exception as ex:
                    log.warning("[crawl4ai] failed: %s -> %s", u, ex)


        await asyncio.gather(*[_one(u) for u in urls])

    log.info(
        f"[crawl4ai] fetched {len(urls)} urls in {loop.time() - t0:.2f}s (concurrency={concurrency}) | total time"
    )

    return docs
