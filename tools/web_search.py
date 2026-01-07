"""Search the web using DuckDuckGo HTML interface directly.

No external dependencies beyond requests (which is standard).
"""

import re
import urllib.parse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.vfs.work_in_progress import WorkInProgressVFS


def get_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Returns a list of results with titles, URLs, and snippets. Use this to find documentation, package names, examples, etc. Compact results after use to save context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 5,
                        "description": "Maximum number of results to return (default: 5)",
                    },
                },
                "required": ["query"],
            },
        },
    }


def execute(vfs: "WorkInProgressVFS", args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query", "")
    max_results = int(args.get("max_results", 5))
    
    if not query:
        return {"success": False, "error": "Query is required"}
    
    try:
        import requests
        
        # Use DuckDuckGo's HTML interface directly
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        response = requests.post(url, data=params, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text
        
        # Parse results using regex (avoiding BeautifulSoup dependency)
        results = []
        
        # Pattern for result blocks in DDG HTML
        # Each result has class="result" with nested elements
        result_pattern = re.compile(
            r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.+?)</a>.*?'
            r'<a class="result__snippet"[^>]*>(.+?)</a>',
            re.DOTALL
        )
        
        for match in result_pattern.finditer(html):
            if len(results) >= max_results:
                break
                
            url_encoded = match.group(1)
            title_html = match.group(2)
            snippet_html = match.group(3)
            
            # Decode DDG's URL redirect
            if "uddg=" in url_encoded:
                url_match = re.search(r'uddg=([^&]+)', url_encoded)
                if url_match:
                    url_decoded = urllib.parse.unquote(url_match.group(1))
                else:
                    url_decoded = url_encoded
            else:
                url_decoded = urllib.parse.unquote(url_encoded)
            
            # Strip HTML tags
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet_html).strip()
            
            results.append({
                "title": title,
                "url": url_decoded,
                "snippet": snippet,
            })
        
        # Estimate tokens (rough: 1 token ≈ 4 chars)
        result_text = str(results)
        token_estimate = len(result_text) // 4
        
        return {
            "success": True,
            "query": query,
            "results": results,
            "count": len(results),
            "_token_estimate": token_estimate,
        }
        
    except ImportError:
        return {
            "success": False, 
            "error": "requests not installed. Run: pip install requests"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
