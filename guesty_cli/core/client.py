"""HTTP Client + Authentication for Guesty API.

Uses stdlib only (urllib.request, json, ssl).
"""

import json
import os
import ssl
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from .config import (
    clear_token_cache,
    count_tokens_last_24h,
    get_cached_token,
    load_config,
    update_token_cache,
)


def build_multipart_body(field_name: str, filename: str, file_bytes: bytes,
                         content_type: str = "application/octet-stream"):
    """Build a multipart/form-data request body for a single file field.

    Returns (body_bytes, content_type_header). Uses a random boundary so the
    delimiter can never collide with the file contents.
    """
    boundary = "----guestycli" + uuid.uuid4().hex
    crlf = b"\r\n"
    parts = [
        b"--" + boundary.encode() + crlf,
        ('Content-Disposition: form-data; name="%s"; filename="%s"' % (field_name, filename)).encode() + crlf,
        ("Content-Type: %s" % content_type).encode() + crlf + crlf,
        file_bytes, crlf,
        b"--" + boundary.encode() + b"--" + crlf,
    ]
    return b"".join(parts), "multipart/form-data; boundary=%s" % boundary


class GuestyError(Exception):
    """Base exception for Guesty API errors."""
    pass


class AuthError(GuestyError):
    """Authentication error."""
    pass


class RateLimitError(GuestyError):
    """Rate limit exceeded."""
    pass


class GuestyClient:
    """HTTP client for Guesty Open API."""
    
    def __init__(self, config: dict = None):
        """Initialize the client.
        
        Args:
            config: Optional config dict. Loads from file if not provided.
        """
        self.config = config or load_config()
        self.base_url = self.config.get("api_base_url", "https://open-api.guesty.com")
        self.api_base = self.base_url.rstrip("/") + "/v1/"  # Guesty Open API v1
        
        # Rate limit tracking
        self.rate_limit_remaining = {
            "second": 15,
            "minute": 120,
            "hour": 5000,
        }
        
        # Direct access token bypass (for agents)
        self._direct_token = os.environ.get('_GUESTY_ACCESS_TOKEN')

        # Circuit breaker for API resilience
        self._circuit_breaker = CircuitBreaker()

        # SSL context (use default, don't skip verification)
        self.ssl_context = ssl.create_default_context()
    
    def _get_auth_url(self) -> str:
        """Get the OAuth token endpoint URL."""
        return urljoin(self.base_url, "/oauth2/token")
    
    def _get_api_url(self, path: str) -> str:
        """Get full API URL for a path."""
        return urljoin(self.api_base, path.lstrip("/"))
    
    def _update_rate_limits(self, headers: dict) -> None:
        """Update rate limit tracking from response headers.
        
        Guesty uses: X-RateLimit-Remaining-Second, -Minute, -Hour
        """
        for period in ["second", "minute", "hour"]:
            header_name = f"X-RateLimit-Remaining-{period.capitalize()}"
            value = headers.get(header_name)
            if value is not None:
                try:
                    self.rate_limit_remaining[period] = int(value)
                except ValueError:
                    pass
    
    def _make_request(
        self,
        method: str,
        url: str,
        data: dict = None,
        headers: dict = None,
        auth: bool = True,
        retry_on_429: bool = True,
        raw_body: bytes = None,
        timeout: int = 30,
    ) -> dict:
        """Make an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            url: Request URL.
            data: Optional request body data.
            headers: Optional additional headers.
            auth: Whether to include auth token.
            retry_on_429: Whether to retry on rate limit.
            
        Returns:
            dict: Response data.
            
        Raises:
            GuestyError: On API errors.
            RateLimitError: If rate limited and retries exhausted.
            AuthError: On authentication failure.
        """
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries + 1):
            # Check circuit breaker before authenticated requests
            if auth:
                try:
                    self._circuit_breaker.check()
                except CircuitBreakerOpen as e:
                    raise GuestyError(str(e))

            # Pre-flight rate limit check — pause if we're running low
            if auth and self.rate_limit_remaining["second"] <= 1:
                time.sleep(1)
            elif auth and self.rate_limit_remaining["minute"] <= 5:
                time.sleep(2)
            
            req_headers = headers.copy() if headers else {}
            
            if auth:
                token = self.get_token()
                req_headers["Authorization"] = f"Bearer {token}"
            
            # Encode data
            body = None
            if raw_body is not None:
                # Caller supplied a pre-built body (e.g. multipart upload) and
                # set its own Content-Type header — don't touch either.
                body = raw_body
            elif data:
                if req_headers.get("Content-Type") == "application/x-www-form-urlencoded":
                    body = urlencode(data).encode("utf-8")
                else:
                    req_headers.setdefault("Content-Type", "application/json")
                    body = json.dumps(data).encode("utf-8")
            
            req = Request(url, data=body, headers=req_headers, method=method)
            
            try:
                with urlopen(req, context=self.ssl_context, timeout=timeout) as response:
                    self._update_rate_limits(dict(response.headers))
                    
                    # Handle empty responses (204 No Content)
                    if response.status == 204:
                        return {}
                    
                    response_data = json.loads(response.read().decode("utf-8"))
                    self._circuit_breaker.record_success()
                    return response_data

            except HTTPError as e:
                self._update_rate_limits(dict(e.headers))
                
                # Handle rate limiting (429)
                if e.code == 429:
                    retry_after = e.headers.get("Retry-After")
                    retry_secs = None
                    if retry_after:
                        try:
                            retry_secs = int(retry_after)
                        except ValueError:
                            retry_secs = None

                    # If Retry-After > 60s, it's a daily/hourly cap — fail immediately
                    # (e.g., Guesty's 5-token-per-day limit returns Retry-After: 83966)
                    max_retry_wait = 60
                    if retry_secs and retry_secs > max_retry_wait:
                        remaining = e.headers.get("RateLimit-Remaining", "?")
                        limit = e.headers.get("RateLimit-Limit", "?")
                        hours = retry_secs / 3600
                        raise RateLimitError(
                            f"Rate limit exceeded ({remaining}/{limit} remaining). "
                            f"Retry after {hours:.1f} hours. "
                            f"Use cached data or wait before retrying."
                        )

                    if retry_on_429 and attempt < max_retries:
                        wait = retry_secs if retry_secs else retry_delay
                        retry_delay *= 2
                        time.sleep(wait)
                        continue
                    else:
                        raise RateLimitError(f"Rate limit exceeded. Retry after: {retry_after or 'unknown'}")
                
                # Handle auth errors (401)
                if e.code == 401:
                    if auth:
                        # API call with expired token — clear cache and retry
                        clear_token_cache()
                        if attempt < max_retries:
                            continue
                    # Token endpoint or retries exhausted
                    raise AuthError(f"Authentication failed: {e.reason}")

                # Handle 400 on token endpoint — don't retry
                if e.code == 400 and not auth:
                    try:
                        error_body = json.loads(e.read().decode("utf-8"))
                        error_msg = error_body.get("errorSummary", error_body.get("message", str(e.reason)))
                    except Exception:
                        error_msg = str(e.reason)
                    raise GuestyError(f"HTTP {e.code}: {error_msg}")

                # Handle other errors
                try:
                    error_body = json.loads(e.read().decode("utf-8"))
                    error_msg = error_body.get("message", error_body.get("errorSummary", error_body.get("error", str(e.reason))))
                except Exception:
                    error_msg = str(e.reason)

                # Record 5xx errors in circuit breaker
                if e.code >= 500:
                    self._circuit_breaker.record_failure()

                raise GuestyError(f"HTTP {e.code}: {error_msg}")

            except URLError as e:
                self._circuit_breaker.record_failure()
                raise GuestyError(f"Network error: {e.reason}")
            
            except json.JSONDecodeError as e:
                raise GuestyError(f"Invalid JSON response: {e}")
        
        raise GuestyError("Max retries exceeded")
    
    def get_token(self, force_refresh: bool = False) -> str:
        """Get a valid access token (cached or fresh).

        Guesty allows max 5 tokens per API key per 24h, each valid for 24h.
        This method aggressively caches to avoid burning token slots:
          1. Direct access token override (--access-token / GUESTY_ACCESS_TOKEN)
          2. Cached token still within validity window (24h minus 5min buffer)
          3. Request a new token (only if absolutely necessary)

        Returns:
            str: Access token.

        Raises:
            AuthError: If authentication fails.
            RateLimitError: If token limit exceeded (5 per 24h).
        """
        # 1. Direct access token bypass (agent-friendly, skip everything)
        if self._direct_token:
            return self._direct_token

        # 2. Always try cached token first — tokens are precious (5/day limit)
        token, expires_at = get_cached_token()
        if token and expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)

                # Return cached token if still valid (5 min buffer for clock skew)
                if not force_refresh and expiry - now > timedelta(minutes=5):
                    return token

                # Even with force_refresh, use cached token if it's not actually expired
                # (force_refresh should only bypass the 5-min buffer, not waste a token slot)
                if force_refresh and expiry > now:
                    return token
            except ValueError:
                pass

        # 3. Local token-generation guard (imperfect — shared across API key users)
        local_count = count_tokens_last_24h()
        if local_count >= 5:
            if token and expires_at:
                # Return expired token as last resort — the API will 401 and we'll
                # handle it in _make_request's retry logic
                return token
            raise RateLimitError(
                "Token limit reached (5 per 24h). This limit is shared across all "
                "apps using this API key. Wait or use --access-token with a pre-obtained token."
            )
        
        # 4. Acquire cross-process lock to prevent parallel token burns
        #    (Guesty only allows 5 tokens/day — parallel processes without a lock
        #    can burn all 5 in one second)
        lock_path = Path(self.config.get("db_path", "")).parent if self.config.get("db_path") else Path.home() / ".guesty-cli"
        lock_file = lock_path / "token.lock"
        lock_acquired = False
        try:
            lock_path.mkdir(parents=True, exist_ok=True)
            # Try to acquire exclusive lock (wait up to 10s)
            lock_fd = os.open(str(lock_file), os.O_CREAT | os.O_WRONLY, 0o600)
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    import fcntl
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                    break
                except (OSError, IOError):
                    # Another process holds the lock — it's refreshing the token
                    # Wait briefly, then re-check the cache (it may have been updated)
                    time.sleep(0.2)
                    token, expires_at = get_cached_token()
                    if token and expires_at:
                        try:
                            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                            if expiry - datetime.now(timezone.utc) > timedelta(minutes=5):
                                os.close(lock_fd)
                                return token  # Another process already refreshed!
                        except ValueError:
                            pass
            if not lock_acquired:
                os.close(lock_fd)
                # Timeout — fall through and try anyway
        except (OSError, ImportError):
            lock_fd = None  # Lock not available (Windows, etc.) — proceed without

        try:
            # Re-check cache one more time (another process may have refreshed while we waited)
            token, expires_at = get_cached_token()
            if token and expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if expiry - datetime.now(timezone.utc) > timedelta(minutes=5):
                        return token
                except ValueError:
                    pass

            # Get new token
            client_id = self.config.get("client_id", "")
            client_secret = self.config.get("client_secret", "")

            if not client_id or not client_secret:
                raise AuthError("Missing client_id or client_secret. Run 'guesty init' to configure.")

            auth_data = {
                "grant_type": "client_credentials",
                "scope": "open-api",
                "client_id": client_id,
                "client_secret": client_secret,
            }

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
            }

            try:
                response = self._make_request(
                    "POST",
                    self._get_auth_url(),
                    data=auth_data,
                    headers=headers,
                    auth=False,
                    retry_on_429=True,
                )
            except GuestyError as e:
                msg = str(e)
                if 'invalid_client' in msg.lower() or '400' in msg:
                    raise AuthError(
                        "Invalid credentials. Your client_id or client_secret may be expired or revoked. "
                        "Check your Guesty Dashboard > Integrations > API and run 'guesty init' to reconfigure."
                    ) from e
                raise AuthError(f"Authentication failed: {msg}") from e

            token = response.get("access_token")
            expires_in = response.get("expires_in", 86400)  # Default 24h

            if not token:
                raise AuthError("No access_token in auth response")

            # Calculate expiry
            now = datetime.now(timezone.utc)
            expiry = now.timestamp() + expires_in
            expires_at = datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat()

            # Cache token (persists to keychain for other processes)
            update_token_cache(token, expires_at)

            return token
        finally:
            # Release cross-process lock
            if lock_acquired and lock_fd is not None:
                try:
                    import fcntl
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
                except (OSError, ImportError):
                    pass
            elif lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
    
    def _parse_response(self, response: Any) -> Any:
        """Parse API response handling different formats.
        
        Guesty uses 3 formats:
        - {"results": [], "count": N} - listings, reservations, etc.
        - {"data": [], "limit": N} - reviews
        - [...] - raw array (owners, webhooks, etc.)
        
        Args:
            response: Raw response data.
            
        Returns:
            Parsed data (list or dict).
        """
        if isinstance(response, list):
            return response
        
        if isinstance(response, dict):
            # Format 1: {"results": [...], "count": N}
            if "results" in response:
                return response["results"]
            
            # Format 2: {"data": [...], "limit": N}
            if "data" in response:
                return response["data"]
            
            # Single object response
            return response
        
        return response
    
    def api_get(self, path: str, params: dict = None) -> Any:
        """Make a GET request to the API.
        
        Args:
            path: API path (e.g., 'listings').
            params: Optional query parameters.
            
        Returns:
            Parsed response data.
        """
        url = self._get_api_url(path)
        
        if params:
            # Handle nested params (like filters)
            query_parts = []
            for key, value in params.items():
                if isinstance(value, (dict, list)):
                    query_parts.append((key, json.dumps(value)))
                else:
                    query_parts.append((key, value))
            
            url = f"{url}?{urlencode(query_parts)}"
        
        response = self._make_request("GET", url)
        return self._parse_response(response)
    
    def api_post(self, path: str, data: dict) -> dict:
        """Make a POST request to the API.
        
        Args:
            path: API path.
            data: Request body data.
            
        Returns:
            Response data.
        """
        url = self._get_api_url(path)
        response = self._make_request("POST", url, data=data)
        return response if isinstance(response, dict) else {"result": response}
    
    def api_put(self, path: str, data: dict) -> dict:
        """Make a PUT request to the API.
        
        Args:
            path: API path.
            data: Request body data.
            
        Returns:
            Response data.
        """
        url = self._get_api_url(path)
        response = self._make_request("PUT", url, data=data)
        return response if isinstance(response, dict) else {"result": response}
    
    def api_delete(self, path: str) -> dict:
        """Make a DELETE request to the API.
        
        Args:
            path: API path.
            
        Returns:
            Response data (usually empty dict).
        """
        url = self._get_api_url(path)
        response = self._make_request("DELETE", url)
        return response if isinstance(response, dict) else {}

    def upload_photo(self, listing_id: str, file_path: str, timeout: int = 120) -> dict:
        """Upload a single photo to a listing via multipart/form-data.

        Returns the raw API response dict (``{"success": True, "data": [...]}``).

        IMPORTANT: ``data[0]`` is NOT reliably the photo you just uploaded —
        Guesty echoes the photo at index 0 (the cover). To find the uploaded
        photo's id, re-list and match the filename embedded in ``source``.
        """
        import mimetypes

        path = str(file_path)
        with open(path, "rb") as fh:
            file_bytes = fh.read()
        filename = os.path.basename(path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body, ct_header = build_multipart_body("file", filename, file_bytes, content_type)
        url = self._get_api_url(
            f"properties-api/property-photos/property-photos/{listing_id}/upload/blob"
        )
        return self._make_request(
            "POST", url, headers={"Content-Type": ct_header},
            raw_body=body, timeout=timeout,
        )

    def api_get_all(self, path: str, params: dict = None, limit: int = 100, max_pages: int = 1000) -> list:
        """Get all records from a paginated endpoint.

        Auto-paginates through all results with loop protection.

        Args:
            path: API path.
            params: Optional query parameters.
            limit: Page size (max 100).
            max_pages: Maximum number of pages to fetch (safety limit).

        Returns:
            list: All records.

        Raises:
            GuestyError: On pagination loop or max pages exceeded.
        """
        all_results = []
        skip = 0
        seen_skips = set()

        for page_num in range(max_pages):
            if skip in seen_skips:
                raise GuestyError(f"Pagination loop detected at skip={skip}")
            seen_skips.add(skip)

            page_params = (params or {}).copy()
            page_params["limit"] = limit
            page_params["skip"] = skip

            # Check circuit breaker before request
            self._circuit_breaker.check()

            response = self._make_request(
                "GET",
                self._get_api_url(path) + "?" + urlencode(page_params),
            )

            results = self._parse_response(response)

            if not isinstance(results, list):
                break

            all_results.extend(results)

            # Check if we've got all results
            if len(results) < limit:
                break

            skip += limit
        else:
            raise GuestyError(f"Pagination exceeded max pages ({max_pages})")

        return all_results
    
    def health_check(self) -> bool:
        """Check API health by making a test request.
        
        Returns:
            bool: True if API is accessible and auth works.
        """
        try:
            # Try to get listings (should be a lightweight call)
            self.api_get("listings", params={"limit": 1})
            return True
        except (GuestyError, AuthError, RateLimitError) as e:
            print(f"Health check failed: {e}")
            return False
