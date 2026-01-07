"""Search the web using DuckDuckGo (no API key required).

Requires: pip install duckduckgo-search
"""

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
                    "region": {
                        "type": "string",
                        "default": "wt-wt",
                        "description": "Region for results (default: 'wt-wt' for no region). Examples: 'us-en', 'uk-en', 'de-de'",
                    },
                },
                "required": ["query"],
            },
        },
    }


def execute(vfs: "WorkInProgressVFS", args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query", "")
    max_results = int(args.get("max_results", 5))
    region = args.get("region", "wt-wt")  # wt-wt = no region, worldwide
    
    if not query:
        return {"success": False, "error": "Query is required"}
    
    try:
        from duckduckgo_search import DDGS
        
        results = []
        ddgs = DDGS()
        # API changed: text() returns list directly, use 'max_results' param
        search_results = ddgs.text(query, region=region, max_results=max_results)
        if search_results:
            for r in search_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
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
            "error": "duckduckgo-search not installed. Run: pip install duckduckgo-search"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
