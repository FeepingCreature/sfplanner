"""GitHub Issues tool for FeepingCreature/sfplanner."""

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.vfs.work_in_progress import WorkInProgressVFS

REPO = "FeepingCreature/sfplanner"
CONFIG_PATH = Path.home() / ".config" / "forge" / "github.json"
KEY_PATH = Path.home() / ".config" / "forge" / "forge-ai-ide.pem"


def get_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "github_issues",
            "description": (
                "Interact with GitHub issues on FeepingCreature/sfplanner. "
                "See tools/GITHUB_ISSUES.md for full documentation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "get", "create", "comment", "close", "reopen", "update"],
                        "description": "Action to perform",
                    },
                    "issue_number": {
                        "type": "integer",
                        "description": "Issue number (required for get/comment/close/reopen/update)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Issue title (required for create, optional for update)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue/comment body in markdown",
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Label names (for create/update/list filter)",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "description": "Filter by state (for list, default: open)",
                    },
                },
                "required": ["action"],
            },
        },
    }


def _load_config() -> dict[str, Any]:
    """Load GitHub App config from XDG config dir."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    if not KEY_PATH.exists():
        raise FileNotFoundError(f"Private key not found: {KEY_PATH}")
    
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    
    config["private_key"] = KEY_PATH.read_text()
    return config


def _get_jwt(app_id: str, private_key: str) -> str:
    """Generate a JWT for GitHub App authentication."""
    import hashlib
    import hmac
    import base64
    
    # JWT header and payload
    header = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued 60 seconds ago (clock skew)
        "exp": now + 600,  # Expires in 10 minutes
        "iss": app_id,
    }
    
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
    
    header_b64 = b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode())
    message = f"{header_b64}.{payload_b64}"
    
    # Sign with RSA - need cryptography library
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        raise ImportError("cryptography library required: pip install cryptography")
    
    private_key_obj = serialization.load_pem_private_key(
        private_key.encode(), password=None
    )
    signature = private_key_obj.sign(  # type: ignore[union-attr]
        message.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    signature_b64 = b64url(signature)
    
    return f"{message}.{signature_b64}"


def _get_installation_token(app_id: str, installation_id: str, private_key: str) -> str:
    """Get an installation access token."""
    import urllib.request
    import urllib.error
    
    jwt = _get_jwt(app_id, private_key)
    
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode())
    
    return data["token"]


def _api_request(
    token: str,
    method: str,
    endpoint: str,
    body: dict[str, Any] | None = None,
) -> Any:
    """Make a GitHub API request."""
    import urllib.request
    import urllib.error
    
    url = f"https://api.github.com{endpoint}"
    
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"GitHub API error {e.code}: {error_body}")


def _format_issue(issue: dict[str, Any], include_body: bool = False) -> dict[str, Any]:
    """Format issue for output."""
    result = {
        "number": issue["number"],
        "title": issue["title"],
        "state": issue["state"],
        "author": issue["user"]["login"],
        "labels": [l["name"] for l in issue.get("labels", [])],
        "created_at": issue["created_at"],
        "updated_at": issue["updated_at"],
        "comments_count": issue.get("comments", 0),
        "url": issue["html_url"],
    }
    if include_body:
        result["body"] = issue.get("body") or ""
    return result


def _format_comment(comment: dict[str, Any]) -> dict[str, Any]:
    """Format comment for output."""
    return {
        "id": comment["id"],
        "author": comment["user"]["login"],
        "body": comment["body"],
        "created_at": comment["created_at"],
    }


def execute(vfs: "WorkInProgressVFS", args: dict[str, Any]) -> dict[str, Any]:
    """Execute the GitHub issues tool."""
    action = args.get("action")
    if not action:
        return {"success": False, "error": "action is required"}
    
    try:
        config = _load_config()
        token = _get_installation_token(
            config["app_id"],
            config["installation_id"],
            config["private_key"],
        )
    except Exception as e:
        return {"success": False, "error": f"Authentication failed: {e}"}
    
    try:
        if action == "list":
            state = args.get("state", "open")
            labels = args.get("labels", [])
            
            endpoint = f"/repos/{REPO}/issues?state={state}"
            if labels:
                endpoint += f"&labels={','.join(labels)}"
            
            issues = _api_request(token, "GET", endpoint)
            # Filter out pull requests (GitHub API returns them as issues too)
            issues = [i for i in issues if "pull_request" not in i]
            
            return {
                "success": True,
                "count": len(issues),
                "issues": [_format_issue(i) for i in issues],
            }
        
        elif action == "get":
            issue_number = args.get("issue_number")
            if not issue_number:
                return {"success": False, "error": "issue_number is required"}
            
            issue = _api_request(token, "GET", f"/repos/{REPO}/issues/{issue_number}")
            comments = _api_request(token, "GET", f"/repos/{REPO}/issues/{issue_number}/comments")
            
            result = _format_issue(issue, include_body=True)
            result["comments"] = [_format_comment(c) for c in comments]
            
            return {"success": True, "issue": result}
        
        elif action == "create":
            title = args.get("title")
            if not title:
                return {"success": False, "error": "title is required"}
            
            body_data: dict[str, Any] = {"title": title}
            if args.get("body"):
                body_data["body"] = args["body"]
            if args.get("labels"):
                body_data["labels"] = args["labels"]
            
            issue = _api_request(token, "POST", f"/repos/{REPO}/issues", body_data)
            
            return {
                "success": True,
                "message": f"Created issue #{issue['number']}",
                "issue": _format_issue(issue, include_body=True),
            }
        
        elif action == "comment":
            issue_number = args.get("issue_number")
            body = args.get("body")
            if not issue_number:
                return {"success": False, "error": "issue_number is required"}
            if not body:
                return {"success": False, "error": "body is required"}
            
            comment = _api_request(
                token, "POST",
                f"/repos/{REPO}/issues/{issue_number}/comments",
                {"body": body},
            )
            
            return {
                "success": True,
                "message": f"Added comment to issue #{issue_number}",
                "comment": _format_comment(comment),
            }
        
        elif action == "close":
            issue_number = args.get("issue_number")
            if not issue_number:
                return {"success": False, "error": "issue_number is required"}
            
            issue = _api_request(
                token, "PATCH",
                f"/repos/{REPO}/issues/{issue_number}",
                {"state": "closed"},
            )
            
            return {
                "success": True,
                "message": f"Closed issue #{issue_number}",
                "issue": _format_issue(issue),
            }
        
        elif action == "reopen":
            issue_number = args.get("issue_number")
            if not issue_number:
                return {"success": False, "error": "issue_number is required"}
            
            issue = _api_request(
                token, "PATCH",
                f"/repos/{REPO}/issues/{issue_number}",
                {"state": "open"},
            )
            
            return {
                "success": True,
                "message": f"Reopened issue #{issue_number}",
                "issue": _format_issue(issue),
            }
        
        elif action == "update":
            issue_number = args.get("issue_number")
            if not issue_number:
                return {"success": False, "error": "issue_number is required"}
            
            body_data: dict[str, Any] = {}
            if args.get("title"):
                body_data["title"] = args["title"]
            if args.get("body"):
                body_data["body"] = args["body"]
            if args.get("labels"):
                body_data["labels"] = args["labels"]
            
            if not body_data:
                return {"success": False, "error": "At least one field to update is required"}
            
            issue = _api_request(
                token, "PATCH",
                f"/repos/{REPO}/issues/{issue_number}",
                body_data,
            )
            
            return {
                "success": True,
                "message": f"Updated issue #{issue_number}",
                "issue": _format_issue(issue, include_body=True),
            }
        
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}