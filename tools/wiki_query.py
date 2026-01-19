"""Search for a wiki page and ask a question about it in one step.

Chains: DuckDuckGo search → find matching wiki page → fetch and query that page.
"""

import re
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.tools.context import ToolContext


def get_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "wiki_query",
            "description": "Search for a wiki page and ask a question about it. Chains: search → find matching page → fetch and answer question. Great for looking up game/technical info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Search term to find the wiki page (e.g., 'Satisfactory Constructor building')",
                    },
                    "page_criterion": {
                        "type": "string",
                        "description": "Criterion to identify the right page from search results (e.g., 'official Satisfactory wiki page about the Constructor')",
                    },
                    "question": {
                        "type": "string",
                        "description": "Question to ask about the wiki page content",
                    },
                },
                "required": ["search_term", "page_criterion", "question"],
            },
        },
    }


def _search_ddg(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search DuckDuckGo using direct HTML interface."""
    try:
        import requests

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

        results = []
        result_pattern = re.compile(
            r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.+?)</a>.*?'
            r'<a class="result__snippet"[^>]*>(.+?)</a>',
            re.DOTALL,
        )

        for match in result_pattern.finditer(html):
            if len(results) >= max_results:
                break

            url_encoded = match.group(1)
            title_html = match.group(2)
            snippet_html = match.group(3)

            # Decode DDG's URL redirect
            if "uddg=" in url_encoded:
                url_match = re.search(r"uddg=([^&]+)", url_encoded)
                if url_match:
                    url_decoded = urllib.parse.unquote(url_match.group(1))
                else:
                    url_decoded = url_encoded
            else:
                url_decoded = urllib.parse.unquote(url_encoded)

            # Strip HTML tags
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()

            results.append({
                "title": title,
                "url": url_decoded,
                "snippet": snippet,
            })

        return results

    except Exception as e:
        return [{"error": str(e)}]


def _fetch_page(url: str) -> tuple[bool, str]:
    """Fetch a webpage and convert to markdown."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; ForgeBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")

        try:
            import html2text

            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0
            content = h.handle(html)
        except ImportError:
            content = re.sub(
                r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
            )
            content = re.sub(
                r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE
            )
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

        max_len = 40000
        if len(content) > max_len:
            content = content[:max_len] + "\n\n[... truncated ...]"

        return True, content

    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"URL error: {e.reason}"
    except Exception as e:
        return False, str(e)


def _ask_model(api_key: str, model: str, prompt: str) -> tuple[bool, str]:
    """Ask the summarization model a question."""
    from forge.llm.client import LLMClient

    try:
        client = LLMClient(api_key, model)
        messages = [{"role": "user", "content": prompt}]
        response = client.chat(messages)

        choices = response.get("choices", [])
        if not choices:
            return False, "No response from model"

        answer = choices[0].get("message", {}).get("content", "")
        return True, answer

    except Exception as e:
        return False, f"Model error: {e}"


def execute(ctx: "ToolContext", args: dict[str, Any]) -> dict[str, Any]:
    from forge.config.settings import Settings

    search_term = args.get("search_term", "")
    page_criterion = args.get("page_criterion", "")
    question = args.get("question", "")

    if not search_term or not page_criterion or not question:
        return {"success": False, "error": "All three parameters are required"}

    settings = Settings()
    api_key = settings.get_api_key()
    model = settings.get_summarization_model()

    if not api_key:
        return {"success": False, "error": "No API key configured"}

    # Step 1: Search DuckDuckGo
    search_results = _search_ddg(search_term)
    if not search_results:
        return {
            "success": False,
            "error": "Search failed: no results",
        }
    if "error" in search_results[0]:
        return {
            "success": False,
            "error": f"Search failed: {search_results[0].get('error', 'unknown error')}",
        }

    # Step 2: Ask model to pick the right URL
    results_text = "\n".join(
        f"- [{r['title']}]({r['url']}): {r['snippet']}" for r in search_results
    )

    pick_prompt = f"""Here are search results for "{search_term}":

{results_text}

Which URL best matches this criterion: {page_criterion}

Reply with ONLY the URL, nothing else. If none match, reply "NONE"."""

    success, picked_url = _ask_model(api_key, model, pick_prompt)
    if not success:
        return {"success": False, "error": f"URL selection failed: {picked_url}"}

    picked_url = picked_url.strip()
    if picked_url == "NONE" or not picked_url.startswith("http"):
        return {
            "success": False,
            "error": f"No matching page found. Results were: {results_text}",
        }

    # Step 3: Fetch the page
    success, content = _fetch_page(picked_url)
    if not success:
        return {"success": False, "error": f"Failed to fetch {picked_url}: {content}"}

    # Step 4: Answer the question
    query_prompt = f"""Here is the content of a wiki page from {picked_url}:

<page_content>
{content}
</page_content>

Based on this page, please answer:

{question}

Be thorough and include specific details like numbers, rates, and requirements."""

    success, answer = _ask_model(api_key, model, query_prompt)
    if not success:
        return {"success": False, "error": f"Query failed: {answer}"}

    return {
        "success": True,
        "search_term": search_term,
        "selected_url": picked_url,
        "question": question,
        "answer": answer,
        "_token_estimate": len(answer) // 4,
    }