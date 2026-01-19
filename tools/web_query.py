"""Fetch a webpage and ask a question about its content using the summarization model."""

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.tools.context import ToolContext


def get_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "web_query",
            "description": "Fetch a webpage and ask a question about its content. Uses the summarization model to analyze the page and answer your question. More efficient than web_fetch when you need specific information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                    "question": {
                        "type": "string",
                        "description": "The question to ask about the webpage content",
                    },
                },
                "required": ["url", "question"],
            },
        },
    }


def _fetch_page(url: str) -> tuple[bool, str]:
    """Fetch a webpage and convert to markdown. Returns (success, content_or_error)."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; ForgeBot/1.0)"}
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
            content = re.sub(
                r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
            )
            content = re.sub(
                r"<style[^>]*>.*?</style>",
                "",
                content,
                flags=re.DOTALL | re.IGNORECASE,
            )
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

        # Truncate if too long (leave room for the model's context)
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


def execute(ctx: "ToolContext", args: dict[str, Any]) -> dict[str, Any]:
    from forge.config.settings import Settings
    from forge.llm.client import LLMClient

    url = args.get("url", "")
    question = args.get("question", "")

    if not url:
        return {"success": False, "error": "URL is required"}
    if not question:
        return {"success": False, "error": "Question is required"}

    # Fetch the webpage
    success, content = _fetch_page(url)
    if not success:
        return {"success": False, "error": content}

    # Get API key and summarization model from settings
    settings = Settings()
    api_key = settings.get_api_key()
    model = settings.get_summarization_model()

    if not api_key:
        return {"success": False, "error": "No API key configured"}

    # Create prompt for the model
    prompt = f"""Here is the content of a webpage from {url}:

<webpage_content>
{content}
</webpage_content>

Based on the webpage content above, please answer this question:

{question}

Provide a clear, concise answer based only on information found in the webpage. If the answer cannot be found in the content, say so."""

    # Call the summarization model
    try:
        client = LLMClient(api_key, model)
        messages = [{"role": "user", "content": prompt}]
        response = client.chat(messages)

        choices = response.get("choices", [])
        if not choices:
            return {"success": False, "error": "No response from model"}

        answer = choices[0].get("message", {}).get("content", "")

        # Estimate tokens for the answer
        token_estimate = len(answer) // 4

        return {
            "success": True,
            "url": url,
            "question": question,
            "answer": answer,
            "_token_estimate": token_estimate,
        }

    except Exception as e:
        return {"success": False, "error": f"Model error: {e}"}