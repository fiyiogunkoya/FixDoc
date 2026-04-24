# FixDoc Architecture

FixDoc is a CLI tool for cloud engineers to capture, search, and share infrastructure fixes. It stores fixes from Terraform, Kubernetes, and other cloud tooling in a searchable, version-controlled JSON+Markdown database at `~/.fixdoc/`.

---

## Table of Contents

1. [Repository Layout](#repository-layout)
2. [Data Flow Overview](#data-flow-overview)
3. [Core Data Model](#core-data-model)
4. [Storage Layer](#storage-layer)
5. [Configuration](#configuration)
6. [Parser System](#parser-system)
7. [Suggestions Engine](#suggestions-engine)
8. [Change Impact Engine](#change-impact-engine)
9. [Pending Error System](#pending-error-system)
10. [Sync System](#sync-system)
11. [Commands — Detailed Reference](#commands--detailed-reference)
    - [capture](#capture)
    - [watch](#watch)
    - [search / show](#search--show)
    - [analyze](#analyze)
    - [analyze (change impact)](#analyze-change-impact)
    - [list / stats](#list--stats)
    - [edit](#edit)
    - [delete](#delete)
    - [pending](#pending)
    - [sync](#sync)
    - [demo](#demo)
12. [Markdown Round-Trip](#markdown-round-trip)
13. [Testing](#testing)

---

## Repository Layout

```
FixDoc/
├── src/
│   └── fixdoc/
│       ├── fix.py                  # Entry point — calls main()
│       ├── cli.py                  # CLI assembly — registers all commands
│       ├── models.py               # Fix dataclass
│       ├── storage.py              # FixRepository — CRUD on fixes.json + docs/
│       ├── config.py               # ConfigManager — reads ~/.fixdoc/config.yaml
│       ├── formatter.py            # Fix → Markdown serialisation
│       ├── markdown_parser.py      # Markdown → Fix deserialisation
│       ├── suggestions.py          # Similar-fix scoring and display
│       ├── change_impact.py        # Change impact scoring engine
│       ├── pending.py              # PendingStore — deferred errors
│       ├── git.py                  # GitOperations wrapper
│       ├── sync_engine.py          # Push/pull/conflict resolution
│       ├── demo_data.py            # Sample errors and Fix objects
│       ├── parsers/
│       │   ├── base.py             # ParsedError, ErrorParser ABC, compute_error_id
│       │   ├── terraform.py        # TerraformParser
│       │   ├── kubernetes.py       # KubernetesParser
│       │   └── router.py           # Auto-detect source, route to parser
│       └── commands/
│           ├── capture.py          # `fixdoc capture`
│           ├── capture_handlers.py # Core capture logic shared by capture + watch
│           ├── watch.py            # `fixdoc watch -- <cmd>`
│           ├── search.py           # `fixdoc search` / `fixdoc show`
│           ├── analyze.py          # `fixdoc analyze <plan.json>`
│           ├── blast_radius.py     # Backward-compat shim (re-exports from change_impact.py)
│           ├── manage.py           # `fixdoc list` / `fixdoc stats`
│           ├── edit.py             # `fixdoc edit <id>`
│           ├── delete.py           # `fixdoc delete`
│           ├── pending.py          # `fixdoc pending [capture|remove|clear]`
│           ├── sync.py             # `fixdoc sync [init|push|pull|status|configure]`
│           └── demo.py             # `fixdoc demo [seed|tour]`
├── tests/
│   ├── fixtures/                   # Terraform plan JSONs, DOT graphs, error text files
│   └── test_integration_terraform.py
├── pyproject.toml
├── pytest.ini
└── CLAUDE.md
```

---

## Data Flow Overview

```
User runs CLI command
        │
        ▼
fix.py → main()
        │
        ▼
cli.py → create_cli()        ← resolves base_path (FIXDOC_HOME or ~/.fixdoc)
        │                    ← loads config via ConfigManager
        │                    ← injects ctx.obj: {base_path, config, config_manager}
        ▼
Command module (e.g. capture.py)
        │
        ├── reads stdin / spawns subprocess
        │
        ├── parsers/router.py → detect_and_parse(text)
        │       └── TerraformParser or KubernetesParser → list[ParsedError]
        │
        ├── suggestions.py → find_similar_fixes(repo, error_text, ...)
        │
        ├── prompt user for issue / resolution / tags
        │
        ├── Fix(issue, resolution, ...) → FixRepository.save(fix)
        │       ├── appends to ~/.fixdoc/fixes.json
        │       └── writes ~/.fixdoc/docs/<id>.md via formatter.py
        │
        └── prints confirmation
```

---

## Core Data Model

**`src/fixdoc/models.py`**

`Fix` is a dataclass that is the single unit of storage throughout the system.

| Field | Type | Source |
|---|---|---|
| `id` | `str` (UUID4) | Auto-generated |
| `issue` | `str` | Required — user input |
| `resolution` | `str` | Required — user input |
| `error_excerpt` | `Optional[str]` | From parser / user input |
| `tags` | `Optional[str]` | Comma-separated string |
| `notes` | `Optional[str]` | User input |
| `author` | `Optional[str]` | From config or prompt |
| `author_email` | `Optional[str]` | From config or prompt |
| `created_at` | `str` (ISO UTC) | Auto-generated |
| `updated_at` | `str` (ISO UTC) | Auto-generated, updated by `touch()` |
| `is_private` | `bool` | Default False — excluded from sync |

**Key methods:**

- `to_dict()` / `from_dict(data)` — JSON serialization via `dataclasses.asdict`.
- `matches(query, match_any=False)` — Searches all text fields. Default: all words must appear (AND). With `match_any=True`: any word suffices (OR).
- `matches_tags(required_tags, match_any=False)` — Tag set intersection logic.
- `matches_resource_type(resource_type)` — Substring match on tags field.
- `summary()` — Short one-line display: `<id[:8]> [tags] - <issue[:40]>`.
- `touch()` — Updates `updated_at` to now.

---

## Storage Layer

**`src/fixdoc/storage.py`**

`FixRepository` is the only component that reads or writes to disk. All commands construct it from `ctx.obj["base_path"]`.

**On-disk layout:**

```
~/.fixdoc/
├── fixes.json          # Canonical database — list of Fix dicts
└── docs/
    ├── <uuid>.md       # One markdown file per fix
    └── ...
```

**Key methods:**

| Method | Behaviour |
|---|---|
| `save(fix)` | Upserts fix in `fixes.json`, generates `docs/<id>.md` via `formatter.py` |
| `get(fix_id)` | Partial-prefix case-insensitive ID lookup |
| `get_by_full_id(fix_id)` | Exact ID match (used by sync) |
| `list_all()` | Returns all fixes sorted by `created_at` descending |
| `search(query)` | Returns fixes where `fix.matches(query)` is True |
| `find_by_resource_type(resource_type)` | Tag substring filter |
| `delete(fix_id)` | Removes from `fixes.json` and deletes `.md` file |
| `list_markdown_files()` | Returns all paths under `docs/` |
| `get_fix_ids()` | Returns set of all IDs (used by sync) |

`fixes.json` is read fully into memory on every operation — appropriate for the expected database size (hundreds to low thousands of fixes).

---

## Configuration

**`src/fixdoc/config.py`**

`~/.fixdoc/config.yaml` holds user settings. The file is created with defaults on first use.

**Config dataclasses:**

| Class | Key fields |
|---|---|
| `UserConfig` | `name`, `email` |
| `SyncConfig` | `remote_url`, `branch` (`main`), `auto_pull` |
| `DisplayConfig` | `search_result_limit`, `list_result_limit`, `top_tags_limit` |
| `CaptureConfig` | `error_excerpt_max_chars`, `max_suggestions_shown`, `similar_fix_limit` |
| `SuggestionWeights` | Seven float weights controlling suggestion scoring |
| `FixDocConfig` | Aggregates all of the above + `private_fixes: list[str]` |

**`resolve_base_path()`** checks the `FIXDOC_HOME` environment variable before defaulting to `~/.fixdoc`. This is the standard override mechanism for tests and non-standard setups.

**CLI context injection:** `cli.py` calls `ConfigManager(base_path).load()` in the root group callback, attaching `config`, `config_manager`, and `base_path` to `ctx.obj`. Every subcommand reads these from context — no command constructs its own config.

---

## Parser System

**`src/fixdoc/parsers/`**

Parsers extract structured information from raw error text. The system is composable: adding a new parser requires only a new file implementing `ErrorParser` and registering it in `router.py`.

### `base.py`

**`ParsedError`** — Unified error representation:

| Field | Description |
|---|---|
| `error_type` | String identifier for the error kind |
| `error_message` | Clean error message |
| `raw_output` | Full original text |
| `resource_type` | e.g. `aws_s3_bucket` |
| `resource_address` | Full Terraform address e.g. `module.app.aws_s3_bucket.main` |
| `error_code` | Provider-specific error code |
| `cloud_provider` | `CloudProvider` enum: AWS / AZURE / GCP / UNKNOWN |
| `severity` | `ErrorSeverity` enum: CRITICAL / ERROR / WARNING / INFO |
| `suggestions` | List of fix suggestion strings |
| `tags` | Pre-populated tags list |
| `error_id` | **Stable 12-char hex hash** of `resource_address + error_code + file + error_message[:160]` — used for deduplication across sessions |

**`ErrorParser`** (ABC) — interface all parsers implement:
- `can_parse(text) -> bool`
- `parse(text) -> list[ParsedError]`
- `parse_single(text) -> Optional[ParsedError]`

### `terraform.py`

Detects Terraform errors by looking for `Error:` / `│ Error:` keywords and `.tf` file references.

**Extraction chain for each error block:**

1. `_extract_resource_info()` — Parses `with <address>` pattern; falls back to scanning for `aws_*`/`azurerm_*`/`google_*` resource type tokens.
2. `_detect_cloud_provider()` — Checks resource type prefix or provider config blocks.
3. `_extract_error_code()` — Priority: explicit `Code:` field → API error pattern → known error code set → HTTP status codes.
4. `_extract_error_message()` — From `Message:` field or first line of error block.
5. `_detect_action()` — Scans for `creating`/`updating`/`deleting` present participles.
6. `_generate_tags()` — Always includes `terraform`; adds provider name, resource type, error code.
7. `_generate_suggestions()` — Cloud-specific advice: IAM permission issues, S3 naming constraints, quota limits, capacity errors, etc.

Predefined code sets: `AWS_ERROR_CODES` and `AZURE_ERROR_CODES` for fast lookup.

### `kubernetes.py`

Detects Kubernetes errors from `kubectl` and `helm` output.

**Sub-parsers:**

| Method | Handles |
|---|---|
| `_is_helm_output()` | Helm-specific keyword detection |
| `_parse_helm_output()` | Extracts release name, chart, error; maps to `ReleaseExists`, `ChartNotFound`, `Timeout`, `RBACDenied` etc. |
| `_parse_kubectl_output()` | `Error from server (...)` and `error when creating` patterns |
| `_parse_pod_status()` | `CrashLoopBackOff`, `ImagePullBackOff`, `OOMKilled`, `Pending` with restart counts and exit codes |
| `_parse_generic_k8s_error()` | Catch-all fallback |

Each status type maps to a pre-defined list of actionable suggestions.

### `router.py`

**`detect_and_parse(text) -> list[ParsedError]`** — Main entry point used by all commands.

Detection order:
1. Helm (Helm keywords take priority)
2. Kubernetes
3. Terraform
4. Generic fallback

`detect_error_source(text)` returns an `ErrorSource` enum value. `get_parser_for_source(source)` returns the appropriate parser instance.

---

## Suggestions Engine

**`src/fixdoc/suggestions.py`**

Before saving a new fix, the system searches the existing database for similar fixes to prevent duplicates and surface relevant past solutions.

**`find_similar_fixes(repo, error_text, tags, limit, weights, min_score, resource_address)`**

Scores each existing fix against the incoming error using a weighted sum:

| Signal | Weight source | Description |
|---|---|---|
| Resource address match | `weights.resource_address` | Exact address in fix issue or excerpt |
| Error code match | `weights.error_code` | Matching error code |
| Message similarity | `weights.error_message` | Jaccard token overlap |
| Resource type | `weights.resource_type` | Same Terraform resource type |
| Tag match | `weights.tag_match` | Shared tags (excluding resource-type tags) |
| Issue keywords | `weights.issue_keyword` | Shared keywords in fix issue text |
| Resolution keywords | `weights.resolution_keyword` | Shared keywords in fix resolution |

Fixes below `min_score` (default 15) are excluded. Results are deduplicated by `(resource_type, error_code, top_tokens)` cluster before returning, capped at `limit` (default 5).

**Helper functions:**
- `_extract_keywords(text)` — Tokenises text, removes stop words and short tokens.
- `_extract_error_codes(text)` — Regex patterns for Azure, AWS, HTTP, and XML error codes.
- `_extract_resource_types(text)` — Finds `aws_*`, `azurerm_*`, `google_*` patterns.

---

## Change Impact Engine

**`src/fixdoc/change_impact.py`**

Estimates infrastructure change impact before `terraform apply`. Combines the Terraform plan JSON, the `terraform graph` DOT dependency graph, and FixDoc fix history into an ImpactScore (0–100).

### Key Concepts

**Control Points** — IAM/RBAC/network resources that act as security and connectivity boundaries. Defined in `CONTROL_POINT_PATTERNS` as prefix → `(category, criticality)` mappings. Uses longest-prefix matching so `google_project_iam_member` matches `google_project_iam`.

Categories: `iam` (AWS IAM roles, policies), `rbac` (Azure role assignments, Key Vault), `network` (security groups, NACLs, firewall rules).

**Impact Layers:**
- **L0** — Resources with actual changes (from plan)
- **L1** — Direct downstream dependents (depth 1 in reverse dependency graph)
- **L2** — Indirect dependents (depth 2+, only populated if L0 has boundary resources or delete/replace actions)

### Scoring Formula

```
score = action_points + impact_points + history_prior

action_points = Σ(ACTION_POINTS[action] × boundary_multiplier × greenfield_multiplier)
impact_points = min(l1_count + l2_count, 25) × impact_multiplier
history_prior = min(history_match_count × 5, 15)
```

**`ACTION_POINTS`:** delete=20, replace=25, update=5, create=8

**Boundary multiplier:** 1.5× for control-point resources

**Greenfield multiplier** (all-create plans):
- Non-boundary creates: 0.3× (new infra is low risk)
- Boundary creates: 0.5× (still risky if misconfigured)
- L1/L2 impact: 0.375× normal (only cross-boundary edges to existing infra count)

**Impact multiplier:**
- Greenfield: 0.375
- All plain updates (no boundary): 0.5
- Otherwise: 1.5

**Severity thresholds:** low (<25), medium (25–49), high (50–74), critical (≥75)

### DOT Graph Parser

`parse_dot_graph(dot_text)` parses `terraform graph` output into forward and reverse adjacency maps. Node names are normalised: `[root]` prefix stripped, `(expand)`/`(close)` suffixes removed.

BFS uses the **reverse adjacency** (who depends on X) to propagate downstream change impact from changed resources.

### History Prior

`compute_history_prior(changed_types, changed_nodes, repo)` — Two-phase lookup, capped at 3 deduplicated matches:

1. **Phase 1 (address match)** — Any fix whose `issue` or `error_excerpt` mentions a changed resource address exactly. Always active.
2. **Phase 2 (resource type + category tags)** — Only fires when L0 has boundary resources or delete/replace actions. Finds fixes by resource type that also have at least one category tag from `_HISTORY_CATEGORY_TAGS` (iam, network, rbac, auth, database, etc.).

Deduplication clusters by CamelCase error fingerprint or first 4 words; keeps the most complete fix (has excerpt, then most recent).

### Redaction

`redact_plan_values(change_block)` masks sensitive data before output:
1. Honours Terraform's `sensitive_values` markers in the plan JSON.
2. Pattern-matches attribute keys against `SENSITIVE_PATTERNS` (password, secret, token, api_key, private_key, access_key, credentials).
3. Replaces matched values with `[REDACTED]`.

### Recommended Checks

`generate_checks(control_points, has_deletes)` emits category-specific checklists:
- `iam` → least-privilege and service account permission reviews
- `rbac` → role assignment scope and key vault policy reviews
- `network` → security group rule verification, open CIDR checks
- Any deletes → cross-stack reference confirmation

---

## Pending Error System

**`src/fixdoc/pending.py`**

Defers error capture for batch processing later. State is stored in `.fixdoc-pending` at the git root (found via `git rev-parse --show-toplevel`).

**`PendingEntry`** fields: `error_id`, `error_type`, `short_message`, `error_excerpt`, `tags`, `resource_address`, `error_code`, `file`, `command`, `deferred_at`.

**`PendingStore`** methods:

| Method | Behaviour |
|---|---|
| `save(entry)` | Upserts by `error_id` |
| `list_all()` | Returns all entries |
| `get(error_id)` | Prefix match |
| `remove(error_id)` | Delete by prefix |
| `clear()` | Delete all |
| `path` | `.fixdoc-pending` absolute path |

`pending_entry_from_parsed_error(err, command)` converts a `ParsedError` into a `PendingEntry`, carrying over all structured fields.

**Lazy creation in watch:** `PendingStore` is only instantiated inside `_handle_multi_error_flow` when a defer action is actually chosen. This avoids interference with `subprocess.Popen` patching in tests.

---

## Sync System

**`src/fixdoc/git.py`** + **`src/fixdoc/sync_engine.py`**

Git-based team fix sharing. Markdown files (not `fixes.json`) are the sync unit — this allows standard git diff/merge tooling to work naturally on fix content.

### Git Operations (`git.py`)

`GitOperations` wraps `subprocess.run` git calls. Key methods:

- `clone(url, branch)` — Initial setup
- `add(paths)` / `add_all()` — Stage changes
- `commit(message, author)` — Create commit
- `push(remote, branch)` / `pull(remote, branch)` — Exchange with remote; pull returns `(had_conflicts, conflicted_files)`
- `get_status(remote, branch)` — Returns `GitStatusInfo` with `commits_ahead`, `commits_behind`, `local_changes`
- `get_file_content_at_ref(path, ref)` — Read file at a git ref (e.g. HEAD before merge)

### Sync Engine (`sync_engine.py`)

**Push flow** (`execute_push`):
1. Identify new/changed fixes (skipping `is_private` fixes and those in `config.private_fixes`)
2. Generate/update markdown files via `formatter.py`
3. `git add` + `git commit` + `git push`

**Pull flow** (`execute_pull`):
1. `git fetch` remote
2. Detect conflicts: both-modified, local-deleted, remote-deleted
3. `git pull` (merge)
4. `rebuild_json_from_markdown()` — Walk `docs/*.md`, parse each via `markdown_parser.py`, merge into local `fixes.json`

**`SyncConflict`** captures `(fix_id, conflict_type, local_fix, remote_fix)`. Conflicts surface to the user for manual resolution rather than silent auto-merge.

---

## Commands — Detailed Reference

### capture

**`src/fixdoc/commands/capture.py`** + **`src/fixdoc/commands/capture_handlers.py`**

Three entry modes:

**Piped mode** (most common):
```bash
terraform apply 2>&1 | fixdoc capture [-t tags]
```
Reads stdin fully, then reopens `/dev/tty` (or `CON` on Windows) to prompt the user for resolution. Calls `handle_piped_input(output, tags, repo, config)` which:
1. Calls `detect_and_parse(output)` via `router.py`
2. Routes to `handle_terraform_capture()` or `handle_kubernetes_capture()` based on detected source
3. Falls back to `handle_generic_piped_capture()` if no structured errors found

**Interactive mode:**
```bash
fixdoc capture [-t tags]
```
Calls `handle_interactive_capture(tags, repo)` which prompts: issue → resolution → tags → notes → error excerpt.

**Quick mode:**
```bash
fixdoc capture -q "S3 bucket name collision | Rename bucket to include account ID" -t aws,s3
```
Calls `handle_quick_capture(quick, tags, repo)` which splits on `|` and saves immediately.

**`capture_single_error(err, output, tags, repo, config)`** — Core Terraform capture path:
1. Displays error card (type, resource, error code, suggestions)
2. Calls `get_similar_fixes_for_error()` to find matches
3. Prompts user to use an existing fix or write a new resolution
4. Saves fix with author from config

**`capture_single_k8s_error(err, output, tags, repo, config)`** — Same flow adapted for Kubernetes ParsedErrors.

---

### watch

**`src/fixdoc/commands/watch.py`**

Wraps any shell command and auto-captures errors on failure.

```bash
fixdoc watch [--tags terraform,prod] [--no-prompt] -- terraform apply -auto-approve
```

**Execution model:**
1. Spawns child process with `subprocess.Popen`, merging stdout+stderr
2. Reader thread streams output to terminal in real-time while buffering
3. Waits for process to exit; preserves the original exit code

**On failure (exit code != 0):**

```
detect_and_parse(buffered_output)
        │
        ├── No errors → generic capture flow (prompt capture/defer/skip)
        │
        ├── 1 error → single-error flow
        │       └── _handle_single_error_flow(errors, output, ...)
        │               ├── --no-prompt: auto-capture all
        │               └── prompt: capture / defer / skip
        │
        └── N errors → multi-error flow
                └── _display_summary_table(errors)
                        │
                        ▼
                    prompt: all / single / skip / defer-all
                        │
                        ▼
                    per-error loop → capture / use existing match / skip / defer
```

**Per-error actions during iteration:**
- **capture** → `capture_single_error()` or `capture_single_k8s_error()`
- **use match** → user selects from `get_similar_fixes_for_error()` results; existing fix is displayed
- **skip** → move to next error
- **defer** → save to `PendingStore` via `pending_entry_from_parsed_error()`

`--no-prompt` flag skips all interactive prompts and auto-captures every detected error.

**`PendingStore` is created lazily** — only instantiated the first time a defer action is chosen, avoiding test mock interference with `subprocess.Popen`.

---

### search / show

**`src/fixdoc/commands/search.py`**

```bash
fixdoc search "s3 bucket" [--limit 10] [--tags aws,s3] [--any-tags] [--any]
fixdoc show <fix_id>
```

**`search`** calls `repo.search(query)` which delegates to `fix.matches()`. Options:
- `--limit` — Max results to display (default from config)
- `--tags` — Filter by tags (AND: all tags must be present)
- `--any-tags` — Switch tag filter to OR mode
- `--any` — Switch query to OR mode (any word matches)

**`show`** calls `repo.get(fix_id)` then renders the full markdown content from `docs/<id>.md` to the terminal.

---

### analyze

**`src/fixdoc/commands/analyze.py`**

```bash
fixdoc analyze plan.json [--format human|json] [--graph graph.dot]
```

`TerraformAnalyzer` loads the plan JSON and cross-references changed resources against the fix database.

**`PlanResource`** fields: `address`, `type`, `action`, `cloud_provider` (detected from resource type prefix).

**`analyze(plan_path)` flow:**
1. Load and parse plan JSON
2. `extract_resources(plan)` — Walks `resource_changes` and `planned_values.root_module`
3. `get_changed_resources(plan)` — Filters to actual changes (excludes `no-op`, `read`, `refresh-only`)
4. For each changed resource type, calls `repo.find_by_resource_type()` to find related past fixes
5. Passes plan to `analyze_change_impact()` from the change impact engine
6. Renders `ImpactResult` in human or JSON format

Human output sections: plan summary → impact score badge → control points → affected resources → recommended checks → fix history matches.

JSON output is suitable for CI/CD pipelines. The `--exit-on` flag enables CI gating.

---

### analyze (change impact)

**`src/fixdoc/commands/analyze.py`** (engine: `src/fixdoc/change_impact.py`)

```bash
fixdoc analyze plan.json [--graph graph.dot] [--format human|json|markdown] [--exit-on low|medium|high|critical]
```

The CLI command for change impact analysis. Features:

**Auto-graph discovery:** If `--graph` is not provided and `terraform` is on `PATH`, the command automatically runs `terraform graph` in the plan's directory and captures the DOT output.

**CI gating via `--exit-on`:** Exits with code 1 if the computed severity meets or exceeds the given threshold. Useful in GitHub Actions:

```yaml
- run: fixdoc analyze plan.json --exit-on high
```

A full example workflow lives at `.github/workflows/terraform-risk-analysis.yml`.

---

### list / stats

**`src/fixdoc/commands/manage.py`**

```bash
fixdoc list [--limit 50]
fixdoc stats
```

**`list`** — Shows all fixes sorted by `created_at` descending using `fix.summary()`. Respects `config.display.list_result_limit`.

**`stats`** — Shows:
- Total fix count
- Fixes with vs. without error excerpts
- Tag frequency distribution (top N tags by count)

---

### edit

**`src/fixdoc/commands/edit.py`**

```bash
fixdoc edit <fix_id> [-i "new issue"] [-r "new resolution"] [-t "new,tags"] [-n "notes"] [-e "excerpt"]
fixdoc edit <fix_id> -I     # interactive mode
```

Flag mode updates only the specified fields. Interactive mode (`-I`) re-prompts all fields with current values as defaults.

After any edit, `fix.touch()` updates `updated_at`, and `repo.save(fix)` persists both JSON and regenerates the markdown file.

---

### delete

**`src/fixdoc/commands/delete.py`**

```bash
fixdoc delete <fix_id> [-y]
fixdoc delete --purge [-y]
```

`delete <fix_id>` — Partial-prefix ID lookup, optional `--yes` to skip confirmation prompt.

`--purge` — Deletes all fixes. Requires confirmation unless `-y` is passed.

---

### pending

**`src/fixdoc/commands/pending.py`**

```bash
fixdoc pending                          # list all deferred errors
fixdoc pending capture <id_or_number>   # capture one
fixdoc pending remove <id_or_number>    # delete one
fixdoc pending clear                    # delete all
```

`<id_or_number>` supports both:
- Error ID prefix (e.g. `a3f9c1`)
- 1-based list position (e.g. `2` refers to the second entry in `fixdoc pending`)

`capture` retrieves the `PendingEntry`, reconstructs a minimal `ParsedError`, calls `capture_single_error()` / `capture_single_k8s_error()`, then removes the entry from the store on success.

`PendingStore` auto-detects git root via `git rev-parse --show-toplevel` and stores `.fixdoc-pending` there.

---

### sync

**`src/fixdoc/commands/sync.py`**

```bash
fixdoc sync init <repo_url>
fixdoc sync push [--message "msg"] [--all]
fixdoc sync pull
fixdoc sync status
fixdoc sync configure [--name "..."] [--email "..."]
```

**`init <repo_url>`** — Clones the remote repo into `~/.fixdoc/` (or configures it as a remote if already a git repo), writes `remote_url` to `config.yaml`.

**`push`** — Identifies fixes to sync (new or changed since last push), writes their markdown files, commits, and pushes. Private fixes (`is_private=True` or listed in `config.private_fixes`) are excluded. `--all` re-pushes all non-private fixes.

**`pull`** — Fetches remote, detects conflicts, merges, then calls `SyncEngine.rebuild_json_from_markdown()` to re-parse all `docs/*.md` files and merge them into the local `fixes.json`. Conflicts are surfaced to the user.

**`status`** — Shows `GitStatusInfo`: commits ahead/behind, local changes, last sync timestamps.

**`configure`** — Updates `UserConfig.name` and `UserConfig.email` in `config.yaml` (used as git commit author).

---

### demo

**`src/fixdoc/commands/demo.py`**

```bash
fixdoc demo seed [--clean]
fixdoc demo tour
```

**`seed`** — Populates the fix database with 6 realistic sample fixes from `demo_data.py`, all tagged with `demo`. `--clean` removes any existing demo-tagged fixes first.

**`tour`** — Interactive guided walkthrough:
1. Captures a sample Terraform AWS error via `handle_piped_input()`
2. Captures a sample Kubernetes error
3. Runs a search demo
4. Shows `list` and `stats` output
5. Demonstrates plan analysis

The tour calls the real capture pipeline, so users experience the actual product behaviour.

---

## Markdown Round-Trip

Fixes are stored in two places simultaneously: `fixes.json` (canonical, fast to query) and `docs/<id>.md` (human-readable, git-diffable). Both representations are always kept in sync by `FixRepository.save()`.

**`formatter.py`** (`fix_to_markdown`) produces:

```markdown
# Fix: <id[:8]>

- **Created**: 2024-01-15T10:30:00+00:00
- **Updated**: 2024-01-15T10:30:00+00:00
- **Author**: Alice <alice@example.com>
- **Tags**: terraform, aws, iam

## Issue

S3 bucket name already taken...

## Resolution

Add account ID suffix to bucket name...

## Error Excerpt

```
Error: creating S3 bucket: BucketAlreadyExists
```

## Notes

Affects staging and prod environments.
```

**`markdown_parser.py`** (`markdown_to_fix`) reverses this exactly. The round-trip is critical for git sync: on `pull`, `rebuild_json_from_markdown()` re-derives `fixes.json` entirely from the markdown files in `docs/`.

---

## Testing

- **372 tests total**: 348 unit + 24 integration
- Tests live in `tests/`; run with `python3 -m pytest`
- Fixtures: `tests/fixtures/terraform/` — 3 plan JSONs, 1 DOT graph, 4 error `.txt` files

**Key patterns:**

- Use `tmp_path` fixture for isolated `FixRepository` instances
- Import command modules via `importlib.import_module("fixdoc.commands.watch")` to avoid `__init__.py` export shadowing
- Patch `subprocess.Popen` via `patch.object(mod.subprocess, "Popen")` — not the global
- For JSON output tests, use `CliRunner(mix_stderr=False)` to isolate stderr notes from stdout JSON
- Python 3.9 target: use `Optional[str]`, not `str | None`
