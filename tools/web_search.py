"""Search the web using DuckDuckGo (no API key required)."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.vfs.work_in_progress import WorkInProgressVFS


def get_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Returns a list of results with titles, URLs, and snippets. Use this to find documentation, package names, examples, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 8,
                        "description": "Maximum number of results to return (default: 8)",
                    },
                },
                "required": ["query"],
            },
        },
    }


def execute(vfs: "WorkInProgressVFS", args: dict[str, Any]) -> dict[str, Any]:
    import urllib.request
    import urllib.parse
    import urllib.error
    import json
    import re
    
    query = args.get("query", "")
    max_results = args.get("max_results", 8)
    
    if not query:
        return {"success": False, "error": "Query is required"}
    
    try:
        # Use DuckDuckGo HTML search (no API key needed)
        # We'll parse the lite version which is simpler
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://lite.duckduckgo.com/lite/?q={encoded_query}"
        
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ForgeBot/1.0)"}
        )
        
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")
        
        # Parse results from DDG lite HTML
        # Results are in <a class="result-link"> tags followed by <td> with snippet
        results = []
        
        # Find all result links - they're in a specific table structure
        # Pattern: <a rel="nofollow" href="URL" class='result-link'>TITLE</a>
        link_pattern = r'<a[^>]*class=[\'"]result-link[\'"][^>]*href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</a>'
        
        # Also try the other order (href before class)
        link_pattern2 = r'<a[^>]*href=[\'"]([^\'"]+)[\'"][^>]*class=[\'"]result-link[\'"][^>]*>([^<]+)</a>'
        
        matches = re.findall(link_pattern, html, re.IGNORECASE)
        matches.extend(re.findall(link_pattern2, html, re.IGNORECASE))
        
        # Get snippets - they follow in <td class="result-snippet">
        snippet_pattern = r'<td[^>]*class=[\'"]result-snippet[\'"][^>]*>([^<]+)</td>'
        snippets = re.findall(snippet_pattern, html, re.IGNORECASE)
        
        for i, (href, title) in enumerate(matches[:max_results]):
            snippet = snippets[i] if i < len(snippets) else ""
            # Clean up
            title = title.strip()
            snippet = snippet.strip()
            # Unescape HTML entities
            import html as html_module
            title = html_module.unescape(title)
            snippet = html_module.unescape(snippet)
            
            results.append({
                "title": title,
                "url": href,
                "snippet": snippet,
            })
        
        if not results:
            # Fallback: try to find any links that look like results
            all_links = re.findall(r'<a[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</a>', html)
            for href, title in all_links[:max_results]:
                if href.startswith('http') and 'duckduckgo' not in href.lower():
                    results.append({
                        "title": title.strip(),
                        "url": href,
                        "snippet": "",
                    })
        
        return {
            "success": True,
            "query": query,
            "results": results,
            "count": len(results),
        }
        
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"URL error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
