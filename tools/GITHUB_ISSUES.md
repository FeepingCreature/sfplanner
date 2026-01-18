# GitHub Issues Tool

Tool for interacting with GitHub issues on FeepingCreature/sfplanner.

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