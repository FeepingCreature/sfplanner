"""Fetch a webpage and convert it to markdown."""

import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.vfs.work_in_progress import WorkInProgressVFS


def get_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a webpage and return its content as markdown. Use this to read documentation, PyPI pages, GitHub READMEs, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                },
                "required": ["url"],
            },
        },
    }


def execute(vfs: "WorkInProgressVFS", args: dict[str, Any]) -> dict[str, Any]:
    import urllib.request
    import urllib.error
    import re
    
    url = args.get("url", "")
    if not url:
        return {"success": False, "error": "URL is required"}
    
    try:
        # Fetch the page
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ForgeBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")
        
        # Try to convert to markdown using html2text if available
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0  # Don't wrap
            content = h.handle(html)
        except ImportError:
            # Fallback: basic HTML tag stripping
            content = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<[^>]+>', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()
            content = f"[html2text not installed - raw text extraction]\n\n{content}"
        
        # Truncate if too long
        max_len = 50000
        if len(content) > max_len:
            content = content[:max_len] + "\n\n[... truncated ...]"
        
        return {"success": True, "content": content, "url": url}
        
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"URL error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
