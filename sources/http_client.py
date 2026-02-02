import os
import random
import time
from urllib.parse import urlparse
import threading
import json
import requests
from typing import Optional, Dict, Any, List

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL = True
except Exception:  # pragma: no cover
    curl_requests = None
    HAS_CURL = False

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except Exception:  # pragma: no cover
    cloudscraper = None
    HAS_CLOUDSCRAPER = False

try:
    from .stealth_headers import SessionFingerprint
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    SessionFingerprint = None


class SmartSession:
    """Requests-compatible session with Cloudflare-aware fallbacks."""

    def __init__(self, timeout: int = 20):
        self._timeout = timeout
        self._aggressive = os.environ.get("SCRAPER_AGGRESSIVE", "1").lower() in {"1", "true", "yes", "on"}
        self._max_retries = int(os.environ.get("SCRAPER_MAX_RETRIES", "2"))
        self._retry_base_delay = float(os.environ.get("SCRAPER_RETRY_BASE_DELAY", "0.5"))
        self._retry_max_delay = float(os.environ.get("SCRAPER_RETRY_MAX_DELAY", "8.0"))
        self._flaresolverr_url = os.environ.get("FLARESOLVERR_URL", "").strip().rstrip("/")
        self._flaresolverr_ttl = float(os.environ.get("FLARESOLVERR_TTL", "1200"))
        self._cache_ttl = int(os.environ.get("SCRAPER_CACHE_TTL", "60"))
        self._cache_max_bytes = int(os.environ.get("SCRAPER_CACHE_MAX_BYTES", str(2 * 1024 * 1024)))
        self._cache_max_entries = int(os.environ.get("SCRAPER_CACHE_MAX_ENTRIES", "256"))
        self._host_max_concurrency = int(os.environ.get("SCRAPER_HOST_MAX_CONCURRENCY", "3"))
        if self._aggressive:
            aggressive_concurrency = int(os.environ.get("SCRAPER_AGGRESSIVE_HOST_CONCURRENCY", "6"))
            self._host_max_concurrency = max(self._host_max_concurrency, aggressive_concurrency)
        self._host_backoff_base = float(os.environ.get("SCRAPER_HOST_BACKOFF_BASE", "5.0"))
        self._host_backoff_max = float(os.environ.get("SCRAPER_HOST_BACKOFF_MAX", "120.0"))
        self._session = requests.Session()
        self._curl_session = curl_requests.Session(impersonate="chrome120") if HAS_CURL else None
        self._cloud_session = cloudscraper.create_scraper() if HAS_CLOUDSCRAPER else None
        # Stealth fingerprint for consistent browser identity
        self._fingerprint = SessionFingerprint() if HAS_STEALTH else None
        self._user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        ]
        self._last_user_agent = self._fingerprint.user_agent if self._fingerprint else random.choice(self._user_agents)
        self._proxy_pool = self._load_proxy_pool()
        self._flare_cache: Dict[str, Dict[str, Any]] = {}
        self._host_cooldowns: Dict[str, Dict[str, Any]] = {}
        self._host_semaphores: Dict[str, threading.Semaphore] = {}
        self._host_lock = threading.Lock()
        self._response_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

    @property
    def headers(self):
        return self._session.headers

    def mount(self, prefix: str, adapter) -> None:
        self._session.mount(prefix, adapter)

    def _load_proxy_pool(self) -> List[Dict[str, str]]:
        raw_list = os.environ.get("SCRAPER_PROXY_LIST", "")
        proxies = []
        if raw_list:
            for entry in raw_list.split(","):
                proxy = entry.strip()
                if not proxy:
                    continue
                proxies.append({"http": proxy, "https": proxy})
        single_proxy = os.environ.get("SCRAPER_PROXY", "").strip()
        if single_proxy:
            proxies.append({"http": single_proxy, "https": single_proxy})
        http_proxy = os.environ.get("SCRAPER_HTTP_PROXY", "").strip()
        https_proxy = os.environ.get("SCRAPER_HTTPS_PROXY", "").strip()
        if http_proxy or https_proxy:
            proxies.append({
                "http": http_proxy or https_proxy,
                "https": https_proxy or http_proxy
            })
        return proxies

    def _pick_proxy(self) -> Optional[Dict[str, str]]:
        if not self._proxy_pool:
            return None
        return random.choice(self._proxy_pool)

    def _get_host(self, url: str) -> str:
        try:
            return urlparse(url).netloc
        except Exception:
            return ""

    def _get_cache_key(self, method: str, url: str) -> str:
        return f"{method}:{url}"

    def _get_cached_entry(self, key: str) -> Optional[Dict[str, Any]]:
        if self._cache_ttl <= 0:
            return None
        with self._cache_lock:
            entry = self._response_cache.get(key)
            if not entry:
                return None
            if entry.get("expires_at", 0) <= time.time():
                self._response_cache.pop(key, None)
                return None
            return entry

    def _store_cache_entry(self, key: str, response) -> None:
        if self._cache_ttl <= 0:
            return
        try:
            content = response.content
            if content is None or len(content) > self._cache_max_bytes:
                return
            headers = dict(response.headers or {})
            cache_control = headers.get("Cache-Control", "")
            max_age = None
            if "max-age=" in cache_control:
                try:
                    max_age = int(cache_control.split("max-age=", 1)[1].split(",", 1)[0])
                except ValueError:
                    max_age = None
            ttl = max_age if max_age is not None else self._cache_ttl
            entry = {
                "status_code": response.status_code,
                "headers": headers,
                "content": content,
                "url": response.url,
                "expires_at": time.time() + ttl
            }
            with self._cache_lock:
                if len(self._response_cache) >= self._cache_max_entries:
                    oldest_key = min(
                        self._response_cache.items(),
                        key=lambda item: item[1].get("expires_at", 0)
                    )[0]
                    self._response_cache.pop(oldest_key, None)
                self._response_cache[key] = entry
        except Exception:
            return

    def _build_cached_response(self, entry: Dict[str, Any]):
        return CachedResponse(
            status_code=entry.get("status_code", 200),
            headers=entry.get("headers", {}),
            content=entry.get("content", b""),
            url=entry.get("url", "")
        )

    def _get_flaresolverr_solution(self, url: str) -> Optional[Dict[str, Any]]:
        if not self._flaresolverr_url:
            return None
        host = self._get_host(url)
        cached = self._flare_cache.get(host)
        if cached and cached.get("expires_at", 0) > time.time():
            return cached.get("solution")

        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        try:
            resp = requests.post(f"{self._flaresolverr_url}/v1", json=payload, timeout=70)
        except Exception:
            return None
        if not resp.ok:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        solution = data.get("solution") or {}
        minimal = {
            "cookies": solution.get("cookies") or [],
            "userAgent": solution.get("userAgent")
        }
        self._flare_cache[host] = {
            "expires_at": time.time() + self._flaresolverr_ttl,
            "solution": minimal
        }
        return minimal

    def _apply_flaresolverr_solution(self, solution: Dict[str, Any], host: str) -> None:
        if not solution:
            return
        user_agent = solution.get("userAgent")
        if user_agent:
            self._session.headers["User-Agent"] = user_agent
            self._last_user_agent = user_agent
        cookies = solution.get("cookies") or []
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            domain = cookie.get("domain") or host
            try:
                self._session.cookies.set(name, value, domain=domain)
            except Exception:
                self._session.cookies.set(name, value)

    def _get_host_semaphore(self, host: str) -> Optional[threading.Semaphore]:
        if not host:
            return None
        with self._host_lock:
            sem = self._host_semaphores.get(host)
            if not sem:
                sem = threading.Semaphore(self._host_max_concurrency)
                self._host_semaphores[host] = sem
            return sem

    def _respect_host_cooldown(self, host: str) -> None:
        if not host:
            return
        entry = self._host_cooldowns.get(host)
        if not entry:
            return
        cooldown_until = entry.get("cooldown_until", 0)
        if cooldown_until > time.time():
            wait_time = cooldown_until - time.time()
            time.sleep(min(wait_time, self._host_backoff_max))

    def _record_host_failure(self, host: str, response) -> None:
        if not host:
            return
        entry = self._host_cooldowns.get(host, {"failures": 0, "cooldown_until": 0})
        entry["failures"] = entry.get("failures", 0) + 1
        cooldown = min(self._host_backoff_base * (2 ** (entry["failures"] - 1)), self._host_backoff_max)
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after_val = float(retry_after)
            except (TypeError, ValueError):
                retry_after_val = None
            if retry_after_val:
                cooldown = max(cooldown, retry_after_val)
        entry["cooldown_until"] = time.time() + cooldown
        self._host_cooldowns[host] = entry

    def _record_host_success(self, host: str) -> None:
        if not host:
            return
        self._host_cooldowns.pop(host, None)

    def _pick_user_agent(self) -> str:
        if random.random() < 0.25:
            self._last_user_agent = random.choice(self._user_agents)
        return self._last_user_agent

    def _merge_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        merged = dict(self._session.headers)
        if headers:
            merged.update(headers)
        if not any(k.lower() == "user-agent" for k in merged.keys()):
            merged["User-Agent"] = self._pick_user_agent()
        return merged

    def _looks_like_cloudflare(self, response) -> bool:
        try:
            server = (response.headers.get("server") or "").lower()
            if "cloudflare" in server:
                return True
            if "cf-ray" in response.headers or "cf-mitigated" in response.headers:
                return True
            text = (response.text or "").lower()
            if "cloudflare" in text and "attention required" in text:
                return True
            if "please enable cookies" in text and "cloudflare" in text:
                return True
        except Exception:
            return False
        return False

    def _is_retryable(self, response) -> bool:
        if response is None:
            return True
        return response.status_code in (408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524)

    def _get_retry_delay(self, response, attempt: int) -> float:
        delay = min(self._retry_base_delay * (2 ** attempt), self._retry_max_delay)
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after_val = float(retry_after)
            except (TypeError, ValueError):
                retry_after_val = None
            if retry_after_val is not None:
                delay = max(delay, retry_after_val)
        jitter = random.uniform(0.0, 0.35)
        return min(delay + jitter, self._retry_max_delay)

    def _should_fallback(self, response) -> bool:
        if response is None:
            return True
        if response.status_code in (429, 503, 520, 521, 522, 523, 524):
            return True
        if response.status_code == 403 and self._looks_like_cloudflare(response):
            return True
        return False

    def _fallback_request(self, method: str, url: str, **kwargs):
        last_error = None
        for session in (self._curl_session, self._cloud_session):
            if not session:
                continue
            try:
                return session.request(method, url, **kwargs)
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        return None

    def request(self, method: str, url: str, **kwargs):
        headers = self._merge_headers(kwargs.pop("headers", None))
        kwargs["headers"] = headers
        kwargs.setdefault("timeout", self._timeout)

        host = self._get_host(url)
        sem = self._get_host_semaphore(host)

        last_error = None
        response = None

        for attempt in range(self._max_retries + 1):
            if sem:
                sem.acquire()
            try:
                request_kwargs = dict(kwargs)
                proxy = self._pick_proxy()
                if proxy:
                    request_kwargs["proxies"] = proxy

                self._respect_host_cooldown(host)

                cache_key = None
                cached_entry = None
                if method.upper() == "GET" and self._cache_ttl > 0:
                    cache_key = self._get_cache_key(method.upper(), url)
                    cached_entry = self._get_cached_entry(cache_key)
                    if cached_entry:
                        etag = cached_entry.get("headers", {}).get("ETag")
                        last_modified = cached_entry.get("headers", {}).get("Last-Modified")
                        if etag and "If-None-Match" not in request_kwargs["headers"]:
                            request_kwargs["headers"]["If-None-Match"] = etag
                        if last_modified and "If-Modified-Since" not in request_kwargs["headers"]:
                            request_kwargs["headers"]["If-Modified-Since"] = last_modified

                try:
                    response = self._session.request(method, url, **request_kwargs)
                except requests.RequestException as exc:
                    last_error = exc
                    response = None

                if self._should_fallback(response):
                    try:
                        fallback = self._fallback_request(method, url, **request_kwargs)
                        if fallback is not None:
                            response = fallback
                            last_error = None
                    except Exception as exc:
                        last_error = exc

                if response is not None and self._looks_like_cloudflare(response):
                    solution = self._get_flaresolverr_solution(url)
                    if solution:
                        self._apply_flaresolverr_solution(solution, self._get_host(url))
                        try:
                            response = self._session.request(method, url, **request_kwargs)
                            last_error = None
                        except requests.RequestException as exc:
                            last_error = exc

                if response is not None and response.status_code == 304 and cached_entry:
                    return self._build_cached_response(cached_entry)

                if response is not None and response.ok:
                    self._record_host_success(host)
                elif response is not None and (self._looks_like_cloudflare(response) or self._is_retryable(response)):
                    self._record_host_failure(host, response)

                if response is not None and response.ok and cache_key:
                    try:
                        content_type = (response.headers.get("Content-Type") or "").lower()
                        if "text/" in content_type or "application/json" in content_type:
                            self._store_cache_entry(cache_key, response)
                    except Exception:
                        pass

                if response is not None and not self._is_retryable(response):
                    return response

                if attempt < self._max_retries:
                    time.sleep(self._get_retry_delay(response, attempt))
            finally:
                if sem:
                    sem.release()

        if response is not None:
            return response
        if last_error:
            raise last_error
        raise requests.RequestException("Request failed without response")

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def head(self, url: str, **kwargs):
        return self.request("HEAD", url, **kwargs)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass
        for session in (self._curl_session, self._cloud_session):
            try:
                session.close()
            except Exception:
                pass


class CachedResponse:
    def __init__(self, status_code: int, headers: Dict[str, str], content: bytes, url: str):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.url = url
        self.ok = 200 <= self.status_code < 400

    @property
    def text(self) -> str:
        try:
            return self.content.decode("utf-8")
        except Exception:
            return self.content.decode("utf-8", errors="ignore")

    def json(self):
        return json.loads(self.text or "{}")
