"""通用 API Client: 重试 + 超时 + UA。所有 collector 复用, 不重复写 requests。"""
import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class APIClient:
    def __init__(self, timeout: float = 30.0, max_retries: int = 3,
                 user_agent: Optional[str] = None):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        if user_agent:
            self.session.headers["User-Agent"] = user_agent

    def get(self, url: str, params: Optional[dict] = None,
            headers: Optional[dict] = None, timeout: Optional[float] = None,
            raw: bool = False) -> Any:
        last_exc: Optional[Exception] = None
        t = timeout or self.timeout
        for attempt in range(self.max_retries):
            try:
                r = self.session.get(url, params=params, headers=headers, timeout=t)
                r.raise_for_status()
                return r if raw else r.json()
            except Exception as e:  # noqa: BLE001 — 网络/HTTP/解析统一重试
                last_exc = e
                if attempt == self.max_retries - 1:
                    break
                time.sleep(2 ** attempt)
        raise last_exc  # type: ignore[misc]

    def get_text(self, url: str, params: Optional[dict] = None,
                 headers: Optional[dict] = None,
                 timeout: Optional[float] = None) -> str:
        r = self.get(url, params=params, headers=headers, timeout=timeout, raw=True)
        return r.text
