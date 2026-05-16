---
name: drift_detector
description: Detect documentation drift by comparing AI-generated endpoint docs against stale/existing documentation, flagging removed fields, renamed fields, and undocumented parameters.
version: 1.0.0
---

# drift_detector

Compares `generated_docs.json` against a `stale_docs.md` file (existing human-written
documentation) and writes `breaking_changes.json` + `breaking_changes.md`.

## Scripts

| File                        | Purpose                                                    |
|-----------------------------|------------------------------------------------------------|
| `scripts/main.py`           | Entry point — orchestrates comparison and report writing   |
| `scripts/comparator.py`     | Field-level diff logic (removed, renamed, undocumented)    |
| `scripts/report_generator.py` | Formats findings into Markdown and engineering alerts    |

## Usage

```bash
python skills/drift_detector/scripts/main.py
```

Reads `output/generated_docs.json` and (optionally) a stale docs file.
Writes to `output/breaking_changes.json` and `output/breaking_changes.md`.

## Issue types detected

| Type                            | Severity | Description                                      |
|---------------------------------|----------|--------------------------------------------------|
| `REMOVED_FIELD`                 | HIGH     | Field present in stale docs but missing from code |
| `POSSIBLE_RENAMED_FIELD`        | MEDIUM   | Field name changed (fuzzy match)                  |
| `UNDOCUMENTED_RESPONSE_FIELD`   | LOW      | Field in code not mentioned in existing docs      |
| `UNDOCUMENTED_QUERY_OR_REQUEST_FIELD` | LOW | Query param or request field with no docs        |

## Output schema (`breaking_changes.json`)

```json
{
  "metadata": {
    "endpoints_analyzed": 87,
    "drift_issues_found": 12,
    "high_severity_issues": 3
  },
  "drift_results": [
    {
      "endpoint": "/api/v1/search",
      "method": "GET",
      "severity": "HIGH",
      "issues": [
        {
          "type": "REMOVED_FIELD",
          "severity": "HIGH",
          "field": "legacy_id",
          "suggested_replacement": "product_id",
          "detail": "..."
        }
      ]
    }
  ],
  "alerts": ["[HIGH] GET /api/v1/search — REMOVED_FIELD: legacy_id ..."]
}
```

## Notes

- If no stale docs file is found, the detector runs in **schema-only mode**: it flags
  undocumented fields found in code that have no AI-generated description.
- The `alerts` list is formatted as PR-comment-ready engineering notices.
