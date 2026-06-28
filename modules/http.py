from __future__ import annotations

from curl_cffi import requests as curl_requests

class HttpClient:
    def __init__(self, proxy: str | None = None, impersonate: str = "safari180"):
        self.proxy = proxy
        self._session = curl_requests.Session(impersonate=impersonate, default_headers=False)
        if proxy:
            self._session.proxies = {"https": proxy, "http": proxy}

    def get(self, url, params=None, headers=None):
        resp = self._session.get(url, params=params, headers=headers or {})
        return resp.json()

    def close(self):
        try:
            self._session.close()
        except Exception:
            pass
