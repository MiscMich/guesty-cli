"""HTTP Client + Authentication for Guesty API.

Uses stdlib only (urllib.request, json, ssl).
"""

import json
import ssl
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from .config import (
    clear_token_cache,
    count_tokens_last_24h,
    get_cached_token,
    load_config,
    update_token_cache,
)


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
        self.api_base = urljoin(self.base_url, "/v1/")
        
        # Rate limit tracking
        self.rate_limit_remaining = {
            "second": 15,
            "minute": 120,
            "hour": 5000,
        }
        
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
            req_headers = headers.copy() if headers else {}
            
            if auth:
                token = self.get_token()
                req_headers["Authorization"] = f"Bearer {token}"
            
            # Encode data
            body = None
            if data:
                if req_headers.get("Content-Type") == "application/x-www-form-urlencoded":
                    body = urlencode(data).encode("utf-8")
                else:
                    req_headers.setdefault("Content-Type", "application/json")
                    body = json.dumps(data).encode("utf-8")
            
            req = Request(url, data=body, headers=req_headers, method=method)
            
            try:
                with urlopen(req, context=self.ssl_context, timeout=30) as response:
                    self._update_rate_limits(dict(response.headers))
                    
                    # Handle empty responses (204 No Content)
                    if response.status == 204:
                        return {}
                    
                    response_data = json.loads(response.read().decode("utf-8"))
                    return response_data
                    
            except HTTPError as e:
                self._update_rate_limits(dict(e.headers))
                
                # Handle rate limiting (429)
                if e.code == 429:
                    if retry_on_429 and attempt < max_retries:
                        # Get retry-after header
                        retry_after = e.headers.get("Retry-After")
                        if retry_after:
                            wait = int(retry_after)
                        else:
                            # Exponential backoff
                            wait = retry_delay
                            retry_delay *= 2
                        
                        time.sleep(wait)
                        continue
                    else:
                        raise RateLimitError(f"Rate limit exceeded. Retry after: {e.headers.get('Retry-After', 'unknown')}")
                
                # Handle auth errors (401)
                if e.code == 401:
                    clear_token_cache()
                    if attempt < max_retries:
                        # Retry with fresh token
                        continue
                    raise AuthError(f"Authentication failed: {e.reason}")
                
                # Handle other errors
                try:
                    error_body = json.loads(e.read().decode("utf-8"))
                    error_msg = error_body.get("message", error_body.get("error", str(e.reason)))
                except:
                    error_msg = str(e.reason)
                
                raise GuestyError(f"HTTP {e.code}: {error_msg}")
                
            except URLError as e:
                raise GuestyError(f"Network error: {e.reason}")
            
            except json.JSONDecodeError as e:
                raise GuestyError(f"Invalid JSON response: {e}")
        
        raise GuestyError("Max retries exceeded")
    
    def get_token(self) -> str:
        """Get a valid access token (cached or fresh).
        
        Returns:
            str: Access token.
            
        Raises:
            AuthError: If authentication fails.
            RateLimitError: If token limit exceeded (5 per 24h).
        """
        # Check for cached token
        token, expires_at = get_cached_token()
        
        if token and expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                
                # Return cached token if still valid (with 5 min buffer)
                if expiry - now > timedelta(minutes=5):
                    return token
            except ValueError:
                pass
        
        # Check token limit (max 5 per 24h)
        if count_tokens_last_24h() >= 5:
            # If we have a cached token that's not expired, use it
            if token and expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    if expiry > now:
                        return token
                except ValueError:
                    pass
            raise RateLimitError("Token limit reached (5 per 24h). Please wait before authenticating.")
        
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
        
        response = self._make_request(
            "POST",
            self._get_auth_url(),
            data=auth_data,
            headers=headers,
            auth=False,
            retry_on_429=True,
        )
        
        token = response.get("access_token")
        expires_in = response.get("expires_in", 86400)  # Default 24h
        
        if not token:
            raise AuthError("No access_token in auth response")
        
        # Calculate expiry
        now = datetime.now(timezone.utc)
        expiry = now.timestamp() + expires_in
        expires_at = datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat()
        
        # Cache token
        update_token_cache(token, expires_at)
        
        return token
    
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
    
    def api_get_all(self, path: str, params: dict = None, limit: int = 100) -> list:
        """Get all records from a paginated endpoint.
        
        Auto-paginates through all results.
        
        Args:
            path: API path.
            params: Optional query parameters.
            limit: Page size (max 100).
            
        Returns:
            list: All records.
        """
        all_results = []
        skip = 0
        
        while True:
            page_params = (params or {}).copy()
            page_params["limit"] = limit
            page_params["skip"] = skip
            
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


# Need to import timedelta after the class definition for type hints
from datetime import timedelta