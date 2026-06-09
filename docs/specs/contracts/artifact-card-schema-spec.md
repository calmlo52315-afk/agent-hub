# Artifact Card Schema Spec

## 1. Goal

Define the frontend-facing artifact card schema used by Stage 5 to render preview cards, diff cards, review cards, and downloadable bundles inside the chat UI.

This schema is produced by Gateway or Artifact Agent normalized output and consumed by the frontend artifact panel.

## 2. Design Principles

- One card schema MUST support the main artifact display types used in MVP.
- Cards MUST be renderable without requiring the frontend to understand internal runtime objects.
- Cards SHOULD support progressive status updates such as `generating` -> `ready` -> `failed`.
- Cards MAY embed action metadata so the UI can render buttons consistently.

## 3. Base Card Schema

```json
{
  "schema_version": "1.0",
  "card_id": "card_001",
  "artifact_id": "artifact_001",
  "session_id": "sess_001",
  "task_id": "task_001",
  "card_type": "preview|diff|file|review|bundle",
  "title": "Login Page Preview",
  "summary": "Dark themed login page with responsive layout",
  "status": "generating|ready|failed",
  "created_at": "2026-06-05T10:00:00Z",
  "updated_at": "2026-06-05T10:01:00Z",
  "producer": {
    "type": "gateway|artifact-agent|review-agent",
    "id": "artifact-agent"
  },
  "badges": ["review-passed", "preview-ready"],
  "actions": [
    {
      "action": "open_preview",
      "label": "Open Preview",
      "enabled": true
    }
  ],
  "content": {}
}
```

## 4. Common Fields

- `card_id`: unique UI card identifier.
- `artifact_id`: artifact bundle identifier.
- `session_id`: session owner of this card.
- `task_id`: task owner of this card.
- `card_type`: discriminates the `content` schema.
- `title`: short card title for chat list and panel header.
- `summary`: short user-facing summary.
- `status`: render state of the card.
- `producer`: who produced or normalized the card.
- `badges`: lightweight semantic tags for UI chips.
- `actions`: button metadata for the UI.
- `content`: type-specific payload.

## 5. Action Schema

```json
{
  "action": "open_preview|open_diff|open_file|download_bundle|retry",
  "label": "string",
  "enabled": true,
  "target": {
    "url": "string",
    "path": "string",
    "tab": "preview|diff|files|review"
  }
}
```

## 6. Card Types

### 6.1 `preview`

```json
{
  "preview_url": "http://localhost:3000",
  "entry_path": "workspace/task_001/preview/index.html",
  "viewport": "desktop|mobile",
  "framework": "nextjs|react|static"
}
```

### 6.2 `diff`

```json
{
  "files_changed": 2,
  "additions": 40,
  "deletions": 8,
  "files": [
    {
      "path": "apps/web/login.tsx",
      "change_type": "create|update|delete",
      "diff_excerpt": "@@ ..."
    }
  ]
}
```

### 6.3 `file`

```json
{
  "path": "workspace/task_001/artifacts/report.md",
  "mime_type": "text/markdown",
  "size_bytes": 1024,
  "download_url": "/artifacts/report.md"
}
```

### 6.4 `review`

```json
{
  "decision": "pass|fail",
  "score": 92,
  "issues": [
    {
      "severity": "high|medium|low",
      "message": "string",
      "paths": ["string"]
    }
  ]
}
```

### 6.5 `bundle`

```json
{
  "archive_path": "workspace/task_001/artifacts/bundle.zip",
  "download_url": "/artifacts/bundle.zip",
  "items": [
    {
      "type": "preview|diff|file|review",
      "artifact_id": "artifact_001"
    }
  ]
}
```

## 7. Rendering Rules

- Frontend MUST use `card_type` to decide which renderer to mount.
- Unknown `card_type` values SHOULD fall back to a generic metadata card instead of crashing the UI.
- `status=generating` SHOULD render a loading state.
- `status=failed` SHOULD render error summary and retry action when allowed.
- `review` cards SHOULD be displayed even when `decision=fail`.

## 8. Validation Rules

- Base fields MUST always be present.
- `content` MUST match the declared `card_type`.
- `preview_url` MUST be present for `preview` cards in `ready` state.
- `diff.files` MUST contain at least one item for `diff` cards in `ready` state.
- `download_url` MUST be present for downloadable `file` and `bundle` cards.

## 9. References

- `docs/specs/ADR/ADR-004-artifact-storage.md`
- `docs/specs/ADR/ADR-020-WebSocket Protocol`
- `docs/specs/contracts/websocket-message-spec.md`
