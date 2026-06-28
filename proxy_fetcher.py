import requests

def fetch_webshare_proxies(api_key: str, limit: int = 10) -> list[str]:
    """
    Fetch live proxies from Webshare API.
    Returns list of proxy strings in format: username:password@host:port
    """
    url = "https://proxy.webshare.io/api/v2/proxy/list/"
    headers = {"Authorization": f"Token {api_key}"}
    params = {"page": 1, "page_size": limit}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        proxies = []
        for item in data.get("results", []):
            # Build proxy string
            username = item.get("username")
            password = item.get("password")
            host = item.get("proxy_address")
            port = item.get("port")
            # Use first protocol (http or socks5)
            protocol = item.get("protocols", [{}])[0].get("protocol", "http")
            proxies.append(f"{protocol}://{username}:{password}@{host}:{port}")
        return proxies
    except Exception as e:
        print(f"Failed to fetch Webshare proxies: {e}")
        return []
