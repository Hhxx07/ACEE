"""Task 4.2: Network/HTTP tools (MCP style)."""

import json
from .registry import register_tool


async def fetch_url(url: str, method: str = "GET") -> str:
    """Fetch content from a URL."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.request(method, url)
            content_type = resp.headers.get("content-type", "")
            body = resp.text
            if len(body) > 5000:
                body = body[:5000] + f"\n... [truncated, total {len(resp.text)} chars]"
            return (
                f"HTTP {resp.status_code} {resp.reason_phrase}\n"
                f"Content-Type: {content_type}\n\n{body}"
            )
    except Exception as e:
        return f"[Error] Fetch failed: {e}"


async def call_rest_api(url: str, method: str = "GET", body: str = "") -> str:
    """Call a REST API endpoint and return the JSON response."""
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        data = body if body else None
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.request(method, url, content=data, headers=headers)
            try:
                j = resp.json()
                return json.dumps(j, indent=2, ensure_ascii=False)[:5000]
            except Exception:
                return resp.text[:5000]
    except Exception as e:
        return f"[Error] API call failed: {e}"


def register_all():
    register_tool(
        name="fetch_url",
        description="Fetch the content of a web page or URL. Returns HTTP status and body text.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
                "method": {"type": "string", "description": "HTTP method", "default": "GET"},
            },
            "required": ["url"],
        },
        handler=fetch_url,
        permission="ASK",
    )
    register_tool(
        name="call_rest_api",
        description="Call a REST API endpoint. Send JSON body and receive JSON response.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "API endpoint URL"},
                "method": {"type": "string", "description": "HTTP method (GET, POST, PUT, DELETE)", "default": "GET"},
                "body": {"type": "string", "description": "JSON request body (for POST/PUT)", "default": ""},
            },
            "required": ["url"],
        },
        handler=call_rest_api,
        permission="ASK",
    )
