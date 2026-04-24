# FixDoc Roadmap

## Shipped

### Core CLI (v1)
- `fixdoc capture` — pipe or interactive/quick entry modes
- `fixdoc search` — full-text keyword search + `fixdoc show`
- `fixdoc list` + `fixdoc stats` — browse and tag distribution
- `fixdoc edit` + `fixdoc delete` — manage fixes
- `fixdoc demo seed|tour` — sample data and interactive walkthrough
- JSON database (`~/.fixdoc/fixes.json`) + Markdown files (`~/.fixdoc/docs/`)
- Config: `~/.fixdoc/config.yaml`, `FIXDOC_HOME` env override

### Team Sync
- `fixdoc sync init|push|pull|status` — git-based team sharing via Markdown files
- Bidirectional Markdown ↔ Fix object conversion (`formatter.py`, `markdown_parser.py`)
- Conflict detection (both-modified, deleted-on-one-side cases)
- Private fixes (`is_private` flag) excluded from sync

### Error Parsers
- Terraform parser v2: cascading address extraction (7 patterns), `TF_CONFIG_ERRORS` dict, init/lock/provider detection
- Pattern 5: `with provider["registry.../namespace/name"]` → `provider.<name>` (supports `.alias` suffix)
- Kubernetes parser + generic fallback
- `ParsedError.error_id` — stable 12-char hex hash for deduplication

### Change Impact / Risk Analysis (`fixdoc analyze`)
- Terraform plan JSON analysis with optional DOT dependency graph
- BFS propagation through resource dependency graph
- Sigmoid impact score (0–100): LOW / MEDIUM / HIGH / CRITICAL
- Control point detection (IAM/RBAC/network boundaries)
- `--format human|json|markdown` output
- `--exit-on` severity gating for CI pipelines
- Sensitive value redaction before output

### Smart Fix Matching v2
- `find_relevant_fixes()` with 7-tier scoring: error_code (150), address (120), attribute (100), category (80), type+action (60), type_tag (40), type_text (20)
- Recency (+30 < 90 days) and module path (+20) bonuses
- Confidence bands: high / medium / low
- `generate_contextual_checks()` with attr-specific, history-derived, and category-fallback checks
- `extract_change_fingerprint()` before/after semantic diffing with `ATTR_CATEGORIES`

### IAM Update Scoring
- Layer 1 (+8): any sensitive IAM field changed
- Layer 2: +10 per new AWS service principal, +20 per cross-account ARN, wildcard `"*"` floors score at 50
- Greenfield saturation cap: score ≤ 45 when no control points change in net-new deploys

### Score Explanation
- `ScoreExplanation` dataclass (label, delta, kind) — mirrors score computation
- `_format_human()` renders "Why this scored X:" block
- `--ai-explain` flag: calls `claude-haiku-4-5-20251001` for polished bullet explanation (optional: `pip install fixdoc[ai]`)

### AI Plan Narrative (Layer 4)
- `generate_ai_narrative()` — 2–3 sentence plain-English plan summary at the top of human output
- Activated by the same `--ai-explain` flag; shown before score explanation bullets
- Includes resource types/actions, control points, downstream count, contextual checks, known issue patterns

### Watch Command
- `fixdoc watch -- <command>` — wraps any CLI command
- Defer-first on failure: all errors auto-deferred to `.fixdoc-pending` without prompting
- Session summary card with optional `[c]` to capture immediately or `[s]` to skip
- Success-path resolver: auto-resolves deferred errors on next clean run
- `--no-prompt` for non-interactive CI; preserves original exit code
- `session_id` (8-char hex) per invocation; `supersede_context()` marks stale pending entries

### Pending System
- `.fixdoc-pending` JSON at git root — `PendingStore` with CRUD + prefix matching
- `PendingEntry` fields: session_id, status, command_family, kind (resource / terraform_config / terraform_init)
- `fixdoc pending list|capture|remove|clear`
- `fixdoc resolve` — standalone command to document fixes for all deferred errors in cwd

### Bulk Import
- `fixdoc import jira file.csv|file.json`
- `fixdoc import servicenow file.json` (JSON only)
- `fixdoc import notion --token TOKEN --database DB_ID` (API-based, stdlib only)
  - Section-aware body extraction (Fix/Mitigation/Resolution headings)
  - `--title-field`, `--resolution-field`, `--status-field`, `--done-values` overrides
- `fixdoc import slack --token TOKEN --channel C0XXX` (API-based, stdlib only)
  - Two-emoji convention: 🔴 on issue root, ✅ on fix reply
  - Custom emoji, 90-day lookback, multi-step resolution formatting
- Duplicate guard via `source:system:id` tags (O(1) per run)
- Review mode (default) and `--auto` (applies low-signal filter)
- `--dry-run`, `--max`, `--tags`

### Apply Outcome Learning (v1 — Observational)
- `fixdoc outcome record-apply|list|show`
- `compute_plan_fingerprint()` — 16-char SHA256 prefix, order-independent
- `.fixdoc-outcomes` JSON at git root
- `fixdoc analyze --record [--pr N] [--commit SHA]` — saves analysis as trackable outcome
- Post-analysis: queries prior failure outcomes and surfaces them as "Historical Apply Outcomes"
- Observational only in v1 — outcomes displayed, not yet used to alter impact scores

### GitHub Actions CI
- `terraform-risk-analysis.yml` — matrix of 7 analyze scenarios on PRs
  - Three review modes: `advisory` (default), `warn`, `gate`
  - Collapsible `<details>` per scenario in PR comments, idempotent via HTML marker
  - Job summaries + artifact uploads
- `terraform-apply-outcome.yml` — records apply results post-merge, links to PR analysis via fingerprint

### Fix Effectiveness Tracking
- `Fix` model: `applied_count`, `success_count`, `last_applied_at` fields + `effectiveness_rate` property
- Watch success path increments both applied_count and success_count; failure path increments only applied_count
- Proven fixes (≥2 applications, ≥75% rate) get +10 score boost in `find_similar_fixes()`
- Low-performing fixes (≥3 applications, <25% rate) get −5 score penalty
- Markdown formatter renders Effectiveness section (Applied / Successful / Rate)

### LLM Error Diagnosis (`--diagnose`)
- `fixdoc watch --diagnose -- <command>` — Claude API explains errors inline on failure
- `diagnosis.py` engine: lazy `import anthropic`, `claude-haiku-4-5-20251001`, max_tokens=300
- Configurable via `diagnosis.enabled`, `diagnosis.max_errors`, `diagnosis.model` in config.yaml
- Also activates via `ANTHROPIC_API_KEY` env var + config toggle

### Slack Push on Error Match (`--notify`)
- `fixdoc watch --notify -- <command>` — posts to Slack when errors match known fixes
- `notifications.py` engine: Block Kit messages via `chat.postMessage`, urllib-only (no deps)
- Header with error count/command/cwd, error list (cap 5), fix suggestions (cap 3)
- 429 retry with `Retry-After` header (max 3 attempts)
- Configurable via `notification.slack_enabled`, `slack_token`, `slack_channel`, `slack_min_matches`
- `SLACK_TOKEN` env var or config; minimum match threshold before sending

### Scenario Matrix
- **01–04**: Existing LocalStack scenarios
- **05–10**: Watch scenarios (multi-error, noisy output, parallelism, language errors, dedup, IAM deny)
- **11–17**: Analyze scenarios (greenfield cap, IAM chain BFS, replace cascade, bad plan, no-op, huge plan, word boundary)
- `bash scenarios/run_all.sh` runner with LocalStack health check

### Developer Experience
- `Makefile` with 14 targets: `setup`, `test`, `test-unit`, `test-integration`, `lint`, `fmt`, `localstack-up/down/health`, `scenarios`, `clean`
- `scripts/setup-dev.sh`: prerequisite checks (Python 3.9+, Docker, Terraform 1.5+)
- `pytest --cov`, Black, Ruff configured; 946 tests

---

## Planned / Backlog

### Apply Outcome Learning v2 — Active Scoring
- Use historical failure outcomes to adjust impact scores (not just display them)
- Confidence decay over time (recent failures weighted higher)
- Threshold tuning from outcome data

### Cross-Stack Dependency Tracking
- Track dependencies across multiple Terraform state files / workspaces
- Propagate change impact across workspace boundaries
- Configurable workspace topology map

### Deeper Impact Analysis
- Historical risk scoring from accumulated outcome data
- Anomaly detection: flag changes that diverge from previous successful patterns
- Resource age / last-changed metadata in score computation

### Plugin / Parser Extensions
- Pluggable parser interface for non-Terraform tools (Pulumi, CDK, Ansible)
- Community parser registry

### Fix Suggestion Quality
- Active learning from `[s]kip` signals during watch/review to down-rank poor suggestions

### FixDoc Cloud / Team Dashboard
- Shared team fix database without requiring a git remote
- Trend dashboards: MTTR, top recurring error types, fix coverage by resource type
- Access controls and fix attribution

---

## Recently Removed from Roadmap (Shipped)

- **Similar-fix suggestions** — shipped as `suggestions.py` with tag/keyword/error-code scoring
- **CI + PR comments** — shipped via `terraform-risk-analysis.yml` GitHub Actions workflow
- **Slack import** — shipped as `fixdoc import slack`
- **Webhook / notification alerts** — shipped as `--notify` flag on `fixdoc watch` with Slack Block Kit integration
- **Outcome-driven suggestion re-ranking** — shipped as effectiveness tracking (applied_count/success_count boost in `find_similar_fixes`)
