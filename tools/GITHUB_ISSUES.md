# GitHub Issues Tool

Tool for interacting with GitHub issues on FeepingCreature/sfplanner.

## Issue Management Workflow

### Checking for New Activity

Use the `check` action - it does all the comparison automatically:

```
github_issues(action="check")
```

Returns:
- `new_issues`: Issues we haven't seen before
- `updated_issues`: Issues with activity since we last looked
- `summary`: "3 new, 2 updated, 5 unchanged"

### Typical Session Flow

```
1. github_issues(action="check")
   → "2 new, 1 updated, 4 unchanged"

2. For new/updated issues:
   github_issues(action="get", issue_number=N)
   → Full issue with comments (auto-marks as seen)

3. Respond:
   - Implement if straightforward
   - Or comment with questions (auto-marks as awaiting_feedback)
   - Or add to ISSUES.md if blocked/complex

4. No manual timestamp updates needed - get/comment auto-update seen.json
```

### State Files

**ISSUES.md** (repo root): Human-readable tracking for blocked/complex issues only
- Issues that need design decisions or are blocked on external factors
- Don't need to track every issue here - just the ones that can't be auto-handled

**.forge/github_issues_seen.json**: Auto-managed timestamps
```json
{
  "issues": {
    "7": {"last_seen_at": "2026-01-18T14:19:51Z", "status": "awaiting_feedback"},
    "8": {"last_seen_at": "2026-01-18T14:19:52Z", "status": "seen"}
  }
}
```

Status values:
- `seen`: We've read it
- `awaiting_feedback`: We commented and are waiting for response
- `closed`: Issue is closed

### Auto-Tracking

The tool automatically updates seen.json:
- `get`: Marks issue as "seen" with current timestamp
- `comment`: Marks issue as "awaiting_feedback" with new timestamp
- `close`: Marks issue as "closed"

This means the `check` action accurately detects when humans respond to our comments.

### Closing the Loop

When an issue is fully resolved:
1. Comment with explanation and commit links
2. Close on GitHub: `github_issues(action="close", issue_number=N)`
3. Remove from ISSUES.md if it was there

## Configuration

Create `~/.config/forge/github.json`:

```json
{
  "app_id": "123456",
  "installation_id": "12345678"
}
```

Also place your GitHub App private key at `~/.config/forge/forge-ai-ide.pem`.

### Getting These Values

1. **App ID**: Found on your GitHub App's settings page (General tab)
2. **Installation ID**: After installing the app on the repo, go to `https://github.com/settings/installations`, click your app, the ID is in the URL (e.g., `.../installations/12345678`)
3. **Private Key**: Generate in App settings under "Private keys", save as `forge-ai-ide.pem`

## Operations

### List Issues

```
github_issues(action="list")
github_issues(action="list", state="closed")
github_issues(action="list", labels=["bug", "enhancement"])
```

Parameters:
- `state`: "open" (default), "closed", or "all"
- `labels`: List of label names to filter by

### Get Single Issue

```
github_issues(action="get", issue_number=42)
```

Returns full issue details including body and comments.

### Create Issue

```
github_issues(action="create", title="Bug: something broken", body="Details here", labels=["bug"])
```

Parameters:
- `title`: Required
- `body`: Optional markdown body
- `labels`: Optional list of label names

### Add Comment

```
github_issues(action="comment", issue_number=42, body="My comment here")
```

### Close Issue

```
github_issues(action="close", issue_number=42)
```

### Reopen Issue

```
github_issues(action="reopen", issue_number=42)
```

### Update Issue

```
github_issues(action="update", issue_number=42, title="New title", body="New body", labels=["bug"])
```

All parameters optional - only provided fields are updated.