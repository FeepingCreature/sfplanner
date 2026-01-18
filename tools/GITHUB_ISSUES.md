# GitHub Issues Tool

Tool for interacting with GitHub issues on FeepingCreature/sfplanner.

## Issue Management Workflow

### Checking for New Activity

1. **List open issues**: `github_issues(action="list")`
2. **Compare with ISSUES.md**: Check if any issues are missing from our tracking
3. **Check for new comments**: For tracked issues, compare `updated_at` with `.forge/github_issues_seen.json`
4. **Review new activity**: Fetch issues with new comments, read and respond

### Typical Session Flow

```
1. "Check GitHub issues" →
   - List all open issues
   - Compare against ISSUES.md and seen timestamps
   - Report: "3 new issues, 2 issues have new comments"

2. For new issues →
   - Read full issue
   - Either: implement if straightforward, OR add to ISSUES.md with questions

3. For issues with new comments →
   - Read the new comments
   - Continue the conversation (implement, ask follow-ups, etc.)

4. After responding to an issue →
   - Update `.forge/github_issues_seen.json` with current timestamp
   - Update ISSUES.md status if needed
```

### State Files

**ISSUES.md** (repo root): Human-readable tracking of issue status
- "Awaiting Feedback" - AI asked questions, waiting for human
- "Blocked / Complex" - Needs design work or external input
- "Recently Completed" - Done this session

**.forge/github_issues_seen.json**: Machine-readable timestamps
```json
{
  "issues": {
    "7": {"last_seen_at": "2026-01-18T14:19:51Z"},
    "8": {"last_seen_at": "2026-01-18T14:19:52Z"}
  }
}
```

### Closing the Loop

When an issue is fully resolved:
1. Close on GitHub: `github_issues(action="close", issue_number=N)`
2. Add explanatory comment with commit links
3. Remove from ISSUES.md (or move to "Recently Completed")
4. Remove from seen.json (optional, doesn't hurt to keep)

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