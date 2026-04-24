# `fixdoc watch` — Command Wrapper for Auto Error Capture

## Context

FixDoc currently requires engineers to manually pipe errors (`terraform apply 2>&1 | fixdoc capture`) or use interactive mode. This creates friction — when a command fails, the engineer has to remember to re-run it with the pipe. `fixdoc watch` removes this friction by wrapping commands to automatically capture output on failure.

## Approach

A single **`fixdoc watch`** command that wraps any command, captures its merged stdout+stderr stream, and on failure routes it through the existing capture pipeline.

```
$ fixdoc watch -- terraform apply
```

**Behavior:**
1. Runs the command as a subprocess
2. Streams merged stdout+stderr to terminal in real-time (user sees output normally)
3. Tees the merged stream to a buffer in the background
4. If exit code != 0: asks "Capture this error? [Y/n]", then pipes captured output through `handle_piped_input()` (existing capture pipeline)
5. If exit code == 0: completely silent, no extra output
6. Returns the original exit code (transparent to scripts/CI)

---

## Implementation Plan

### 1. Create `fixdoc watch` command

**New file:** `src/fixdoc/commands/watch.py`

Click command with these characteristics:
- Uses `@click.argument("command", nargs=-1, required=True)` to accept the wrapped command after `--`
- Uses `subprocess.Popen` with `stdout=subprocess.PIPE, stderr=subprocess.STDOUT` to merge streams
- A reader thread reads from the subprocess, writes each line to the terminal AND appends to a buffer
- After process exits, checks exit code
- On failure: shows captured output summary, asks `Capture this error? [Y/n]`
  - If yes: calls `handle_piped_input(captured_output, tags=None, repo=repo, config=config)` from existing `capture_handlers.py`
  - Saves the returned Fix via `FixRepository.save()`
- On success: exits silently with exit code 0
- Always exits with the wrapped command's exit code via `sys.exit(exit_code)`

**Options:**
- `--tags, -t` — pre-set tags passed through to capture handler
- `--no-prompt` — skip the "Capture?" confirmation, go straight to capture flow on failure

### 2. Wire into CLI

**File:** `src/fixdoc/cli.py`
- Import `watch` from `src/fixdoc/commands/watch.py`
- Add `cli.add_command(watch)`

**File:** `src/fixdoc/commands/__init__.py`
- Export `watch`

### 3. Tests

**New file:** `tests/test_watch.py`

Test cases using `CliRunner` and mocked subprocess:
- Command succeeds (exit 0) → no output from fixdoc, exit code 0
- Command fails (exit 1) → prompts for capture, creates Fix
- Command fails + user declines capture → no Fix created, exit code preserved
- `--no-prompt` flag skips confirmation
- `--tags` flag passes tags through to capture handler
- Merged stdout+stderr is displayed to terminal in real-time
- Exit code from wrapped command is preserved
- No command provided → Click error
- Command not found → handles gracefully

---

## Files to Create
| File | Purpose |
|------|---------|
| `src/fixdoc/commands/watch.py` | `fixdoc watch -- CMD` wrapper command |
| `tests/test_watch.py` | Watch command tests |

## Files to Modify
| File | Change |
|------|--------|
| `src/fixdoc/cli.py` | Register `watch` command |
| `src/fixdoc/commands/__init__.py` | Export `watch` |

## Existing Code to Reuse
| What | Where |
|------|-------|
| `handle_piped_input()` | `src/fixdoc/commands/capture_handlers.py` — process captured output on failure |
| `FixRepository` | `src/fixdoc/storage.py` — save the resulting Fix |
| `detect_error_source()` | `src/fixdoc/parsers/router.py` — used internally by handle_piped_input |
| `prompt_similar_fixes()` | `src/fixdoc/suggestions.py` — used internally by handle_piped_input |
| Click context pattern | `ctx.obj["base_path"]`, `ctx.obj["config"]` for repo + config access |

---

## UX Example

```bash
$ fixdoc watch -- terraform apply

Initializing the backend...

Error: creating S3 Bucket (my-bucket): BucketAlreadyExists
  The requested bucket name is not available.

──────────────────────────────────────────────────
Command failed (exit code 1). Capture this error? [Y/n] y

──────────────────────────────────────────────────
Captured from Terraform:

  Provider: AWS
  Resource: aws_s3_bucket.my_bucket
  Code:     BucketAlreadyExists
  Error:    The requested bucket name is not available

  Suggestions:
    • Use a unique bucket name with region/account prefix
──────────────────────────────────────────────────

 What fixed this? added random suffix to bucket name
Tags [aws,terraform,s3,BucketAlreadyExists]:
Notes (optional):

Fix saved: a3f8c921
```

Successful command — completely transparent:
```bash
$ fixdoc watch -- terraform plan
# ... normal terraform output, nothing extra from fixdoc ...
$ echo $?
0
```

---

## Verification

1. `pytest` — all existing 210 tests still pass
2. `pytest tests/test_watch.py` — new tests pass
3. Manual: `fixdoc watch -- ls /nonexistent` — captures error, offers to save
4. Manual: `fixdoc watch -- echo "hello"` — succeeds silently, exit code 0
5. Manual: verify `echo $?` after `fixdoc watch -- false` returns 1

## Implementation Order

1. Create `src/fixdoc/commands/watch.py` with the watch command
2. Update `src/fixdoc/commands/__init__.py` to export it
3. Update `src/fixdoc/cli.py` to register it
4. Create `tests/test_watch.py`
5. Run full test suite to verify no regressions

---

# Smart Fix Capture Timing (Failure→Success Flow)

## Context

`fixdoc watch` previously prompted "What fixed this?" immediately after a failure — the worst time. Engineers debug and retry multiple times before knowing the fix. This plan shifts capture to **after a failure→success cycle**: auto-defer on failure, then ask "what fixed it?" on the next successful run.

## Summary

| Feature | Description |
|---|---|
| Auto-defer on failure | All errors (structured + generic) are automatically saved to `.fixdoc-pending` without prompting |
| Success-path resolver | On next successful run with matching cwd + command family, offers to document what fixed deferred errors |
| `fixdoc resolve` command | Standalone command to document fixes for deferred errors in current directory |
| `_command_family()` | Extracts first 2 non-flag tokens from a command string for fuzzy matching |
| `find_by_context()` | Finds pending entries matching cwd + command family within a 24h window |
| `find_by_cwd()` | Finds all pending entries for a directory (used by `resolve`) |

## Files Changed

- `src/fixdoc/pending.py` — `cwd` field on `PendingEntry`, `_command_family()`, `find_by_context()`, `find_by_cwd()`, updated `pending_entry_from_parsed_error()`
- `src/fixdoc/commands/_resolve_flow.py` — new shared `resolve_pending_entries()` used by watch + resolve
- `src/fixdoc/commands/watch.py` — defer-first failure path; success-path resolver
- `src/fixdoc/commands/resolve.py` — new `fixdoc resolve` command
- `src/fixdoc/commands/__init__.py` — added `resolve` export
- `src/fixdoc/cli.py` — registered `resolve` command
- `tests/test_pending_smart.py` — 31 new tests for cwd field + helper functions
- `tests/test_watch.py` — full rewrite for defer-first behavior (25 tests)
- `tests/test_resolve.py` — 9 new tests for resolve command
- `tests/test_integration_terraform.py` — updated 4 integration tests to match new behavior

## Usage

```bash
# On failure: errors auto-deferred, summary card shown
fixdoc watch -- terraform apply

# On next success: prompted to document what fixed deferred errors
fixdoc watch -- terraform apply

# Or manually resolve at any time
fixdoc resolve
```

---

## Plan Summary: Scenarios 05–10 (Watch Scenarios) — 2026-03-04

Created Terraform fixtures and runner integration for watch scenarios 05–10.

**New files (23 total)**:
- `scenarios/05-watch-multi-failure-missing-vars/` — 2-module setup, 4 missing required vars → 4 plan-time errors
- `scenarios/06-watch-invalid-resources/` — invalid CIDR + non-JSON IAM policy → 2 client-side validation errors
- `scenarios/07-watch-parallelism-bomb/` — 6 S3 buckets with same name, `-parallelism=10` → 5 apply-time collisions
- `scenarios/08-watch-terraform-graph-errors/` — 2 `type=number` vars with string defaults → 2 TF language errors
- `scenarios/09-watch-multi-module-same-error/` — same invalid CIDR in 2 modules → 2 errors with distinct `resource_address`
- `scenarios/10-watch-iam-cascade-deny/` — docs-only (real AWS); README + main.tf + providers.tf + fixtures/expected_errors.txt

**Modified files**:
- `scenarios/run_all.sh` — added `run_watch_scenario`, `run_watch_scenario_plan`, `run_watch_scenario_docs_only` helpers; wired 05–10 calls between scenario 04 and analyze block; updated final echo
- `scenarios/RUNBOOK.md` — updated Expected/Verify sections for 05–09 to reflect defer-first behavior; added watch smoke test to Quick Verification Checklist

**Behavior**: All watch scenarios use `--no-prompt` flag for non-interactive CI runs. On failure, errors are auto-deferred; PASS line printed if `.fixdoc-pending` was created.

---

## Terraform Parser Improvements + Session-Based Pending

### Problem
1. **Parser gap**: Config/init/validation errors (e.g. `Invalid default value for variable`, `Inconsistent dependency lock file`) produced `[unknown]` resource_address because the parser only handled resource-addressed apply/provider errors.
2. **Over-clearing bug**: `watch.py` called `store.clear_context(cwd, family)` at the start of every failure, wiping all pending entries for that (dir + command) — including entries from previous unrelated failures.

### PR 1 — Terraform Parser Improvements (`src/fixdoc/parsers/terraform.py`)
- Added `TF_CONFIG_ERRORS` dict mapping error title fragments → PascalCase codes.
- Pattern 5 in `_extract_resource_info()`: matches `in variable/local/output/module "name"` → sets `resource_address=<scope>.<name>`.
- Pattern 6: matches init/lock/provider error titles → sets `resource_address=terraform.init` for `InconsistentLockFile`, `ModuleNotInstalled`, `ProviderQueryFailed`.
- `_extract_error_code()` fallback: matches error title against `TF_CONFIG_ERRORS` when no provider-specific code found.
- 10 new parser tests in `TestTFConfigErrors`.

### PR 2 — Session-Based Pending
**`src/fixdoc/pending.py`**:
- `PendingEntry` gains 4 new fields: `session_id`, `status` (default `"pending"`), `command_family`, `kind`. All backward-compatible via `from_dict()`.
- `_derive_kind(resource_address)` → `"terraform_init" | "terraform_config" | "resource"`.
- `pending_entry_from_parsed_error()` accepts `session_id` and `command_family` kwargs; derives `kind` automatically.
- `list_all(include_superseded=False)` — default filters to `status="pending"` only.
- `supersede_context(cwd, command_family)` — marks matching `pending` entries as `superseded` (does not delete). Replaces `clear_context()`.
- `find_latest_session(cwd, command_family, max_age_hours=24)` — returns entries from the most recent `session_id` for that context within the age window.

**`src/fixdoc/commands/watch.py`**:
- Generates `session_id = uuid.uuid4().hex[:8]` per watch invocation.
- Computes `family = _command_family(command_str)` once at start.
- On failure: calls `supersede_context` (not `clear_context`); passes `session_id`, `command_family`, `kind` to all `PendingEntry` objects.
- On success: uses `find_latest_session()` instead of `find_by_context()`; after resolving, nudges about older sessions via `find_by_cwd()`.

**Tests**: 43 new tests (pending_smart.py), updated watch + integration tests to reference `supersede_context` / `find_latest_session`. Total: 657 tests.

---

## Plan: Notion Importer (2026-03-06)

Added `fixdoc import notion --token TOKEN --database DB_ID` — API-based importer using `urllib` stdlib (no new runtime deps).

**New files:**
- `src/fixdoc/importers/notion.py` — fetches pages via Notion API, extracts fix fields using ranked property matching, supports body-content fallback when resolution property is empty
- `tests/fixtures/import/notion_sample.json` — 7-page fixture covering all paths (closed, open, missing title, body fallback, custom fields)

**Modified files:**
- `src/fixdoc/commands/import_cmd.py` — added `notion_cmd` subcommand with `--title-field`, `--resolution-field`, `--status-field`, `--done-values` override flags
- `tests/test_importers.py` — added `TestNotionImporter` with 24 tests
- `CLAUDE.md` — updated import system docs and test count

**Key design decisions:**
- 4-tuple return `(fixes, skipped_open, skipped_missing, bad_rows)` to separate open vs missing accounting
- `fetch_blocks_fn` injectable for testing (avoids real HTTP in tests)
- Source tag uses 32-char hex (UUID with hyphens stripped) for clean idempotency key
- Body fallback: empty resolution prop → fetch page blocks → extract plain text; if still empty → `skipped_missing`
- `_find_field` ranked matching: exact normalized key wins over partial containment (e.g. "Status" beats "Ticket Status History")

**Result:** 681 tests, all passing.

---

## Smart Change Impact Analysis — Core Intelligence (2026-03-07)

**Goal:** Replace shallow resource-type-only matching with multi-signal scoring, unify the output, and add context-aware checks.

### What was implemented:
1. **Change Fingerprint Extraction** — `extract_change_fingerprint()` diffs `before` vs `after` at top level, classifies attrs via `ATTR_CATEGORIES` (networking, sizing, iam, etc.). `ImpactNode.change_fingerprint` stores the result. `PlanResource.before_values` added.

2. **Unified Smart Matching** — `find_relevant_fixes()` replaces both `find_resource_prior_fixes()` and `compute_history_prior()`. 7-tier scoring: error_code (150), address (120), attribute (100), category (80), type+action (60), type_tag (40), type_text (20). Bonuses: recency (+30), module_path (+20). Confidence bands: high/medium/low. `match_reason` is structured dict with `supporting_signals`.

3. **Contextual Checks** — `generate_contextual_checks()` replaces `generate_checks()`. Uses `ATTR_CHECKS` for (resource_type, attr) pairs, high-confidence history-derived checks (cap 2), category fallbacks, delete checks.

4. **Output Format** — "Relevant Past Fixes" section with confidence inline. "Contextual Checks" with source tags. JSON output includes `relevant_fixes` and `contextual_checks` plus all legacy keys.

5. **Backward Compatibility** — `resource_warnings`, `history_matches`, `checks` legacy fields populated from new data. Old functions preserved.

### Key decisions:
- Error code match requires resource type context (prevents cross-resource false positives)
- Only high-confidence (or medium + supporting signals) matches feed into impact score history count
- History-derived checks limited to 2, skip generic resolutions (< 20 chars or "fixed it")
- Top-level-only diff for fingerprints (no recursion into nested blocks)

**Result:** 717 tests, all passing.

---

# Notion Importer — Section-Aware Extraction + Integration Tests

## Summary

Added section-aware block extraction to the Notion importer. When a page's resolution property is empty and body blocks are fetched as fallback, the importer now first looks for structured section headings (Fix/Mitigation, Resolution, Root Cause, etc.) and extracts only that section's content. Falls back to full body text if no matching heading found.

## Changes

1. **`src/fixdoc/importers/notion.py`**: Added `_RESOLUTION_SECTION_HEADINGS` constant, `extract_section_text()` function, and updated body fallback in `extract()` to try section extraction before full body.
2. **`tests/fixtures/import/notion_sample.json`**: Updated VPC routing page to have multi-section blocks (Description, Fix/Mitigation, Lessons Learned) for section-aware extraction testing.
3. **`tests/fixtures/import/notion_api_responses.json`**: New fixture with 9 realistic pages covering all extraction scenarios (section headings, full-body fallback, property-wins, empty sections, custom fields, open/closed filtering).
4. **`tests/test_importers.py`**: Replaced mock-heavy Notion tests with fixture-based integration tests. Added `extract_section_text` unit tests + full pipeline integration tests using both fixtures. CLI tests now use the API fixture.

## Key Decisions

- `extract_section_text` returns the *first* matching section (not all), matching the "most relevant fix" heuristic
- Empty section (heading exists but no content before next heading) returns "" to trigger full-body fallback
- Section matching is case-insensitive and uses exact match against candidate list
- Existing `extract_block_text` preserved as-is for full-body fallback

**Result:** 734 tests, all passing.

---

# Upgrade GitHub Actions to PR Review Surface

## Summary

Added `--format markdown` output to `fixdoc analyze` and rewrote the GitHub Actions workflow to post risk analysis directly in PRs.

## What was implemented

1. **`_format_markdown(result)`** in `src/fixdoc/commands/analyze.py` — Pure GitHub-flavored markdown output with severity emojis, metrics table, score explanation (top 3, modifiers filtered), contextual checks (top 3), and relevant past fixes table (top 3). No ANSI codes. Issues truncated at 80 chars.

2. **`--format markdown` CLI option** — Added to `analyze` command's `--format` choices alongside `human` and `json`.

3. **GitHub Actions workflow rewrite** (`.github/workflows/terraform-risk-analysis.yml`) — Matrix strategy across 7 analyze scenarios (11-17), job summaries, aggregated PR comments with collapsible `<details>` per scenario, idempotent comment updates via HTML marker, three review modes (advisory/warn/gate) via `REVIEW_MODE` env var, `GATE_THRESHOLD` for gating severity.

4. **12 new tests** in `tests/test_change_impact.py` (`TestAnalyzeFormatMarkdown`) — header, score/severity, summary table, top-3 caps for explanations/checks/fixes, empty section omission, severity emojis, no-ANSI verification, CLI flag integration, text truncation.

5. **README.md** — Expanded CI Integration section with review modes table, `--exit-on` examples, output formats table.

6. **CLAUDE.md** — Updated workflow description, test count (734 → 746).

**Result:** 746 tests, all passing.

---

# Apply Outcome Learning (v1) — Observational

## Summary

Added the missing feedback loop: record what FixDoc predicted at PR time, capture what actually happened post-apply, link the two, and surface historical outcomes in future analyses. v1 is observational only — outcomes are displayed, not used to alter impact scores.

## Key Files

1. **`src/fixdoc/outcomes.py`** (new) — `Outcome` dataclass, `compute_plan_fingerprint()`, `OutcomeStore` (`.fixdoc-outcomes` at git root).
2. **`src/fixdoc/commands/outcome.py`** (new) — `record-apply`, `list`, `show` CLI commands.
3. **`src/fixdoc/commands/__init__.py`** + **`src/fixdoc/cli.py`** — Wired `outcome` command group.
4. **`src/fixdoc/change_impact.py`** — Added `outcome_matches` field to `ImpactResult`.
5. **`src/fixdoc/commands/analyze.py`** — `--record`/`--pr`/`--commit` options, outcome matching via fingerprint, display in human/JSON/markdown formatters.
6. **`tests/test_outcomes.py`** (new) — 35 tests covering model, fingerprint, store, CLI, and display.
7. **`.github/workflows/terraform-risk-analysis.yml`** — Records analysis outcomes on PR.
8. **`.github/workflows/terraform-apply-outcome.yml`** (new) — Records apply results post-merge.

**Result:** 781 tests, all passing.

---

## Plan 9: Attribute-First Relevance Engine (2026-03-14)

**Goal:** Redesign fix relevance matching around attribute-first, domain-aware philosophy. Suppress low-signal matches (standalone type_text, type_tag, type_action), add 8 tight operational change domains, query-time dedup clustering, and template-based human-readable narratives.

**Three changes:**
1. **Attribute-first matching** — primary signals (error_code 150, address 120, changed_attribute 100, change_domain 70-85, attribute_category 80) can surface fixes alone; secondary boosters (recency +30, module_path +20, resource_family +15, type_tag +15, type_action +10) only add to primary. Standalone type_text/type_tag/type_action fully suppressed.
2. **Query-time dedup** — cluster key `(resource_type, error_code, top_attr, issue_family)` where `issue_family` is an 8-char MD5 of normalized issue text. Best per cluster shown, others counted as `[+N similar fixes]`.
3. **Better presentation** — template-based narratives per signal type with presentation honesty (domain matches use "overlaps with", only error_code/address use definitive "previously encountered"). Markdown and JSON outputs updated.

**Files changed:**
1. **`src/fixdoc/relevance.py`** (new) — `CHANGE_DOMAINS` (8 domains), `RelevanceMatcher` class, `format_match_narrative()`, moved helpers from change_impact.py.
2. **`src/fixdoc/change_impact.py`** — `find_relevant_fixes()` now thin wrapper over `RelevanceMatcher`. Helpers re-exported for backward compat. Legacy functions preserved.
3. **`src/fixdoc/commands/analyze.py`** — `_format_human()` uses narrative templates, `_format_markdown()` uses bullet list (no table), `_format_json()` adds domain/similar_count/narrative. AI prompt extended with match narratives.
4. **`tests/test_relevance.py`** (new) — 51 tests covering primary signals, secondary boosters, dedup clustering, domain matching, narrative templates, presentation honesty, helpers, integration.
5. **`tests/test_change_impact.py`** — Updated existing tests: standalone type_text/tag/action tests now assert suppression, end-to-end tests use primary signals, markdown format tests updated for narrative output.

**Result:** 879 tests, all passing.

---

# Three North Star Features: Fix Surfacing, Auto-Learn, Outcome Scoring

## Context

FixDoc's three engines: Change Intelligence (~85% done), Failure Intelligence, and Memory. These three features close the most impactful gaps.

## Features Implemented

### Feature 1: Surface Relevant Fixes on Watch Failure
- `_show_fix_suggestions()` in `watch.py` calls `find_similar_fixes()` per deferred entry after the summary card
- Shows "Known fixes that may help:" with up to 2 fixes per error, 6 total, deduped across entries
- Shown in both `--no-prompt` and interactive paths
- Passes `error_id` from pending entry for source-error-id boosting

### Feature 2: Auto-Learn from Watch Success
- `Fix.source_error_ids: Optional[list]` field added to `models.py` — links a fix to the pending error IDs it resolved
- `_resolve_flow.py` injects `source_error_ids = [e.error_id for e in group]` before saving
- `formatter.py` renders `## Source Error IDs` section; `markdown_parser.py` parses it back (roundtrip)
- `suggestions.py` `find_similar_fixes()` gains `error_id` param; signal 8: +30 score if `error_id in fix.source_error_ids`

### Feature 3: Outcome-Driven Scoring (v2)
- `compute_impact_score()` gains `outcome_failure_count` param: `+min(count * 10, 25)` after history overlay
- `build_score_explanation()` gains matching param; emits `kind="outcome"` bullet
- `analyze_change_impact()` threads the count through
- `analyze.py` moved outcome query before `analyze_change_impact()` so failure count flows into scoring
- Greenfield cap (45) still applies; wildcard floor (50) still overrides; max from prior experience: history(15) + outcome(25) = 40 pts

## Files Modified
1. `src/fixdoc/change_impact.py` — `compute_impact_score`, `build_score_explanation`, `analyze_change_impact` gain `outcome_failure_count`
2. `src/fixdoc/commands/analyze.py` — outcome query moved before analysis call
3. `src/fixdoc/commands/watch.py` — `_show_fix_suggestions()` helper, calls in both failure paths
4. `src/fixdoc/models.py` — `source_error_ids` field on `Fix`
5. `src/fixdoc/formatter.py` — `## Source Error IDs` section rendering
6. `src/fixdoc/markdown_parser.py` — Source Error IDs section parsing
7. `src/fixdoc/commands/_resolve_flow.py` — injects error IDs into captured fixes
8. `src/fixdoc/suggestions.py` — `error_id` parameter + signal 8 scoring

## Tests Added (30 new)
- `TestOutcomeScoring` (7): zero/1/2/3 failures, combined, greenfield cap, wildcard override
- `TestOutcomeExplanation` (3): bullet shown/capped/zero
- `TestOutcomeDrivenScoring` (2): analyze passes count, backward compat
- `TestWatchFixSurfacing` (8): shows/hides fixes, no-prompt, max-per-error, dedup, arg passing, error_id, ranking
- `TestSourceErrorIds` (4): default/roundtrip/backward compat/in dict
- `TestSourceErrorIdsMarkdown` (3): roundtrip/missing section/multiple IDs
- `TestErrorIdMatch` (3): boost/no-match/none

**Result:** 909 tests, all passing.

---

# Failure Intelligence + Memory Engine: Diagnosis, Effectiveness, Slack Push

## Context

Three features to push Failure Intelligence to ~70% and Memory Engine to ~75%:
1. **Fix Effectiveness Tracking** — Track applied_count/success_count on fixes linked via source_error_ids
2. **LLM Error Diagnosis** — Use Claude API to explain errors during watch failure
3. **Slack Push on Error Match** — Post to Slack when watch detects known fixes

## Files Changed

### Feature 2: Fix Effectiveness Tracking
1. `src/fixdoc/models.py` — `applied_count`, `success_count`, `last_applied_at` fields + `effectiveness_rate` property
2. `src/fixdoc/formatter.py` — `## Effectiveness` section rendering
3. `src/fixdoc/commands/watch.py` — `_track_effectiveness_success()` / `_track_effectiveness_failure()` helpers
4. `src/fixdoc/suggestions.py` — Signal 9: effectiveness boost (+10/-5)

### Feature 1: LLM Error Diagnosis
1. `src/fixdoc/config.py` — `DiagnosisConfig` (enabled, max_errors, model)
2. `src/fixdoc/diagnosis.py` — NEW: `diagnose_error()` + `diagnose_errors()` with lazy anthropic import
3. `src/fixdoc/commands/watch.py` — `--diagnose` flag, `_diagnose_errors_inline()` helper

### Feature 3: Slack Push on Error Match
1. `src/fixdoc/config.py` — `NotificationConfig` (slack_enabled, slack_token, slack_channel, slack_min_matches)
2. `src/fixdoc/notifications.py` — NEW: `_slack_post()`, `_build_blocks()`, `post_slack_notification()`
3. `src/fixdoc/commands/watch.py` — `--notify` flag, `_maybe_notify_slack()` helper, `_show_fix_suggestions_list()` (returns suggestions for Slack reuse)

## Tests Added (32 new)
- `TestEffectiveness` (6): fields default, rate zero/all/partial, roundtrip, backward compat
- `TestWatchEffectivenessTracking` (3): success increments both, failure increments applied only, no linked fixes
- `TestEffectivenessBoost` (1): effective fix ranks higher in suggestions
- `TestDiagnoseError` (6): success, no key, import error, API failure, resource in prompt, truncation
- `TestDiagnoseErrors` (1): limits to max_errors
- `TestWatchDiagnosis` (3): flag calls diagnosis, no flag no diagnosis, no key warning
- `TestBuildBlocks` (4): basic, with suggestions, caps 5 errors, caps 3 suggestions
- `TestSlackPost` (4): success, failure, 429 retry, max retries
- `TestPostSlackNotification` (2): success, failure
- `TestWatchSlackNotification` (2): flag triggers, no flag no notification

**Result:** 941 tests, all passing.

---

# Memory-Worthiness Classifier — Phase 1

## Summary

Added a classifier (`src/fixdoc/classifier.py`) that labels each deferred error as `"memory_worthy"` or `"self_explanatory"`. Self-explanatory errors (e.g. missing required argument, invalid default value) are still stored internally for recurrence detection but hidden from the normal UX.

## What Changed

1. **`PendingEntry.worthiness`** field ("memory_worthy"|"self_explanatory", default "memory_worthy") with backward-compatible `from_dict`. `list_all()` and `find_latest_session()` filter self-explanatory by default via `include_self_explanatory` param.

2. **`Fix.memory_type`** field (default "fix") — forward-compatible for Phase 2 memory types (Check/Playbook/Insight).

3. **`classifier.py`** — `classify_entry(entry, store=None)` with 4-tier classification: recurrence promotion (>=3 similar), kind override (terraform_config/init), error code sets, default by kind. `count_similar_recurrences()` uses normalized matching (same error_code + resource type prefix).

4. **`watch.py`** — Failure path classifies entries before saving, splits display into memory-worthy (numbered list) and self-explanatory (collapsed count). Fix suggestions/diagnosis/Slack only use memory-worthy entries. Success path auto-resolves self-explanatory entries from same session.

5. **`pending.py` CLI** — `--all` flag to show self-explanatory errors; footer shows hidden count.

6. **`resolve.py`** — Auto-resolves self-explanatory entries in cwd after resolving memory-worthy.

## Tests

33 classifier tests + 4 memory_type tests + 6 watch classifier integration tests = 43 new tests.

**Result:** 989 tests, all passing.

---

# Memory Types — Phase 2

## Summary

Phase 2 activates the `memory_type` field on the `Fix` model, auto-classifying resolutions into **fix**, **check**, **playbook**, or **insight** and rendering them differently in watch suggestions and Slack notifications.

## What was implemented

1. **`classify_memory_type(resolution)`** in `classifier.py` — Structure-first classification: playbook (3+ steps) > check (verify/ensure keywords) > insight (explanatory phrases) > fix (default).

2. **`rendering.py`** (new) — `format_suggestion_preview(fix, max_len)` with type-aware rendering: fix=plain, check="Verify: ...", playbook="Playbook (N steps): ...", insight="Context: ...". Stutter prevention strips redundant check keywords.

3. **Watch suggestions** — `_show_fix_suggestions_list()` uses `format_suggestion_preview()` instead of inline truncation.

4. **Slack notifications** — `_build_blocks()` uses `format_suggestion_preview(fix, max_len=80)`.

5. **Capture UX** — `_classify_and_confirm(resolution)` auto-classifies and only prompts for override on non-fix types. Shorthand `[f/c/p/i]` accepted. Integrated into all 5 capture functions.

6. **Markdown round-trip** — `formatter.py` emits `**Memory Type:**` for non-fix types. `markdown_parser.py` extracts it, defaults to "fix".

7. **Tests** — 48 new tests: 35 classifier+rendering, 5 markdown roundtrip, 8 watch+capture integration.

**Result:** 1037 tests, all passing.

---

# Kubernetes Change Intelligence — `fixdoc k8s`

## Summary

Added `fixdoc k8s` command group for analyzing Kubernetes platform change impact before changes are made. V1 covers 4 AKS change types: OS upgrade (Azure Linux 2.0 -> 3.0), K8s version (1.28 -> 1.29), ingress controller (NGINX -> Contour), and node pool SKU changes.

## What was built

1. **Data models** (`src/fixdoc/k8s/models.py`) — 9 dataclasses: BreakingChange, CatalogEntry, NodePool, Workload, IngressResource, ClusterSnapshot, ExposedWorkload, RolloutRisk, K8sImpactResult. All with to_dict()/from_dict().

2. **Change catalog** (`src/fixdoc/k8s/catalog.py`) — Curated knowledge base with 4 AKS change types, each with breaking changes, detection hints, pre/post-checks, and risk factors. Version normalization for flexible matching.

3. **Cluster snapshot** (`src/fixdoc/k8s/snapshot.py`) — kubectl subprocess-based discovery (read-only). Extracts node pools, workloads, ingresses, services, network policies, CRDs, namespaces. Optional helm support. Graceful degradation on failures.

4. **Impact engine** (`src/fixdoc/k8s/engine.py`) — Scoring algorithm: baseline (severity weights x category multiplier, cap 70) + workload exposure (kind-weighted, cap 30) + known-safe discount (-20% if cluster present but no matches) + history prior (3 pts/fix, cap 15). Workload matching via regex-based detection hints. Fix database integration for team knowledge.

5. **Output formatting** (`src/fixdoc/k8s/formatting.py`) — Human, JSON, and markdown formats. Same patterns as analyze command. Markdown uses severity emojis and collapsible sections.

6. **CLI commands** (`src/fixdoc/commands/k8s_cmd.py`) — `fixdoc k8s analyze` (main analysis), `fixdoc k8s snapshot` (capture to JSON), `fixdoc k8s changes` (catalog listing). Supports --cluster, --snapshot, --format, --exit-on (CI gating), --namespace, --kubeconfig.

7. **Tests** — 97 new tests across 3 files: test_k8s_models.py (37), test_k8s_engine.py (30), test_k8s_cli.py (30). Fixture: tests/fixtures/k8s/sample_snapshot.json.

**Result:** 1202 tests, all passing.

---

## YAML Custom Catalog + AI-Assisted Generation for `fixdoc k8s`

### Problem
The K8s change intelligence catalog was hardcoded in Python. Teams couldn't add custom platform change knowledge without editing source code. Even if they could, translating release notes into structured breaking changes with detection hints requires deep platform expertise.

### Solution
1. **YAML-based custom catalog** at `.fixdoc-catalog/` in repo root — file loading, merge with built-ins, version-controlled
2. **AI-assisted catalog generation** via `fixdoc k8s catalog generate` — paste release notes or provide a URL, Claude extracts breaking changes and generates a ready-to-commit YAML file

### Implementation Summary

1. **`CatalogEntry.source` field** (`models.py`) — `source: str = "built-in"` runtime-only field (not serialized in `to_dict()`), set to filename for custom entries

2. **YAML loading + merge** (`catalog.py`) — `_load_yaml_file(path)` handles single-entry (dict with `category`) and multi-entry (dict with `entries`) YAML formats. `load_custom_entries(catalog_dir?)` discovers `.fixdoc-catalog/` at git root. `build_merged_catalog(custom_entries)` merges with override key `(category, from_version, to_version)`. `resolve_change()`, `list_categories()`, `list_changes()` all accept optional `catalog` param.

3. **Engine passthrough** (`engine.py`) — `analyze_k8s_change()` accepts `catalog=None`, passes to `resolve_change()`.

4. **CLI wiring** (`k8s_cmd.py`) — `_get_merged_catalog()` helper loads + merges. `--change` no longer hardcoded Choice (free-text). `k8s changes` shows `[custom]`/`[built-in]` labels. `k8s catalog generate` subcommand with `--from-text`, `--from-url`, and interactive stdin.

5. **AI generation** (`generate.py`) — `generate_catalog_entry()` uses Claude Sonnet (lazy import, max_tokens=2000) with structured prompt including valid hint fields and example. `validate_generated_yaml()` validates output.

6. **Tests** — 42 new tests in `test_k8s_catalog_custom.py`: YAML loading (10), discovery (5), merge (6), resolve (4), CLI changes (3), AI generation (6), CLI generate (4), source field (4). Fixtures: 5 YAML files in `tests/fixtures/k8s/catalog/`.

**Result:** 1244 tests, all passing.

---

## K8s Change Intelligence: Tighten Matching Semantics

**Problem:** Live cluster testing showed the k8s engine's matching was too noisy — generic detection hints (e.g. `resource_requests` with pattern `.`) matched every workload, duplicates inflated scores, and team knowledge retrieval returned unrelated fixes.

**5 Improvements implemented:**

1. **Dedup exposure before scoring** (`engine.py`, `formatting.py`) — Workloads aggregated by `(name, namespace)` before exposure scoring. Each unique entity counted once regardless of how many BCs matched. `cluster_exposure` entries include `match_count`, `confidence`, and optional `all_matches` list. Formatting shows aggregated "Matched by N breaking changes" view.

2. **`applies_to` entity scope** (`engine.py`, `generate.py`) — New optional `applies_to` dict on detection hints with `kinds`, `namespaces`, `names`, `images`, `labels` fields. AND logic across fields, OR within. `_matches_applies_to()` short-circuits at top of `_match_hint_against_workload/ingress()`. Backward compat: absent `applies_to` matches all.

3. **Match confidence** (`engine.py`, `formatting.py`) — `_classify_match_confidence(hint)` returns `"high"`, `"medium"`, or `"low"` based on pattern specificity and `applies_to` presence. Exposure score weighted by confidence (high=1.0, medium=0.5, low=0.25). Low-confidence matches hidden by default in human/markdown output.

4. **Tag tiers for team knowledge** (`engine.py`) — `_K8S_TAG_TIERS` replaces `_K8S_SEARCH_TAGS` (kept as deprecated alias). Fix must match at least 1 required tag (10 pts each) + boost tags (2 pts each). Unknown categories return empty list.

5. **Stricter AI validation** (`generate.py`, `k8s_cmd.py`) — `validate_generated_entry(entry)` warns on: short description/consequence, trivially broad patterns without `applies_to`, invalid fields/regex, missing reason/impact, severity inflation, no detection hints. Warnings displayed after `k8s catalog generate` but don't block write.

**Tests:** 45 new tests added to `test_k8s_engine.py` (confidence: 9, applies_to: 15, dedup: 5, tag tiers: 7, validation: 11). 2 existing tag tests updated for tiered system.

**Result:** 1290 tests, all passing.

---

## K8s Change Intelligence: Round 2 — Semantic Fixes

**Date:** 2026-03-20

4 fixes addressing second-round feedback from live cluster testing:

1. **Controller workload detection + ingress_class matching** (`catalog.py`, `generate.py`) — New `ingress-controller-workload` BC detects the actual nginx controller Deployment/DaemonSet via `images` and `labels` hints scoped with `applies_to: {kinds: [Deployment, DaemonSet]}`. Added `ingress_class` hint to `ingress-nginx-annotations` BC. Added `ingress_class` to `_VALID_HINT_FIELDS`. Scoped TLS `"."` pattern hint with `applies_to: {kinds: [Ingress]}` (was unscoped low-confidence).

2. **Category-specific rollout risk** (`engine.py`, `formatting.py`) — `ingress-controller` category now produces routing-type risk (`type: "routing"`, `ingress_count`, `affected_namespaces`, `has_tls`, `total_pod_estimate`) instead of node-centric risk. Human formatter renders routing-specific output.

3. **Increased token limits** (`generate.py`) — Release notes truncation: 4000 → 12000 chars. AI max_tokens: 2000 → 4000.

4. **Test updates** — 12 new tests: 4 ingress_class matching, 3 controller workload detection, 3 routing rollout risk, 2 TLS hint scoping. 1 existing assertion updated (BC count 3→4).

**Result:** 1302 tests, all passing.

---

# K8s Change Intelligence: Exposure-First Report Redesign

## Summary

Redesigned `format_human()` and `format_markdown()` in `src/fixdoc/k8s/formatting.py` to put actionable information first. The old layout buried cluster exposure under a wall of generic platform risk descriptions.

## Changes

1. **Exposure-first layout** — New section order: Affected Resources → Rollout Risk → Action Items → Platform Context → Team Knowledge. Previously: Platform Risks → Cluster Exposure → Rollout Risk → Pre/Post Checklists → Team Knowledge.

2. **Affected Resources** (replaces "Cluster Exposure") — Shows `impact` text instead of BC IDs. Issue count inline with resource name. Multi-match resources show impact bullets without internal identifiers.

3. **Platform Context** (replaces "Platform Risks") — Condensed to one-liner per BC (`{SEV}  {title}`) when cluster data is present. Full descriptions shown without cluster data or with `--verbose`.

4. **Action Items** (replaces separate Pre/Post checklists) — Merges `pre_checks[:3] + post_checks[:2]` into 5 items max. `--verbose` shows full separate Pre/Post sections.

5. **Score explanation** — Moved to verbose-only in human format.

6. **Markdown** — Affected Resources table with Issues/Impact columns. Platform Context in collapsible `<details>` when cluster data present. Score Breakdown moved after Platform Context.

7. **JSON format** — Unchanged (full data model for programmatic consumers).

## Files Modified

- `src/fixdoc/k8s/formatting.py` — Rewrote `format_human()` and `format_markdown()`
- `tests/test_k8s_cli.py` — Updated section name assertions (Platform Risks → Platform Context, Cluster Exposure → Affected Resources, Pre-Migration Checklist → Action Items)

**Result:** 1302 tests, all passing.

---

# Fix Duplicate Prevention

## Problem
User's `~/.fixdoc/fixes.json` had 102 entries but only 13 unique fixes — 90 were duplicates of the same fix created over many days. Root cause: `FixRepository.save()` only deduplicates by UUID (`fix.id`), but every new `Fix()` gets a fresh `uuid.uuid4()`.

## Solution
Added a `content_hash` field to `Fix` (16-char hex SHA-256 of normalized `issue + resolution`) and check it in `save()` before inserting new fixes. Also added `fixdoc deduplicate` command to clean up existing duplicates.

## Changes
- `src/fixdoc/models.py` — Added `content_hash` field with `__post_init__` auto-computation, `compute_content_hash()`, `_normalize_for_hash()`
- `src/fixdoc/storage.py` — `save()` checks `content_hash` on new inserts, returns existing fix if duplicate found
- `src/fixdoc/commands/capture.py` — Dedup detection message (`saved.id != fix.id`)
- `src/fixdoc/commands/_resolve_flow.py` — Merge `source_error_ids` on dedup
- `src/fixdoc/commands/watch.py` — Dedup detection message
- `src/fixdoc/commands/pending.py` — Dedup detection message
- `src/fixdoc/commands/dedup.py` (new) — `fixdoc deduplicate [--dry-run] [--keep oldest|newest]`
- `src/fixdoc/cli.py` + `src/fixdoc/commands/__init__.py` — Register command
- `tests/test_dedup.py` (new) — 26 tests
- `tests/test_watch.py` — Updated 2 assertions to accept dedup message
- `tests/test_change_impact.py` — Made test fixture resolutions distinct

**Result:** 1328 tests, all passing.

---

# FixDoc SaaS — Phase 0 MVP (2026-04-24)

## Context

FixDoc's CLI is mature (1,328 tests). Adoption friction is the bottleneck: git-based sync, self-managed GitHub Actions, local-only search. Phase 0 turns FixDoc into something a team can adopt in 5 minutes and pay for in 5 weeks, without rewriting engines.

## Decisions

- **Scope:** Phase 0 MVP only (~4 weeks to first paying teams)
- **Auth:** Clerk (JWT verify server-side, React SDK client-side)
- **Hosting:** Railway (backend + Postgres + frontend)
- **Boundary:** CLI stays free/OSS, SaaS opt-in. Backend imports `fixdoc` as a library — no engine duplication.
- **First integration:** GitHub App for zero-config PR comments

## Boundary

**Stays local (free/OSS):** `watch`, `capture`, `analyze`, `k8s analyze`, `resolve`, `~/.fixdoc/` store, git sync fallback, `--diagnose`/`--ai-explain` with user's own API key, self-managed GitHub Actions path.

**Becomes SaaS (Phase 0 paid, opt-in):** team fix database, web UI (dashboard/fixes/pending/settings), `fixdoc login` + `fixdoc team push/pull/search`, GitHub App PR bot.

**Deferred to Phase 1+:** Obsidian importer, Slack App OAuth, centralized AI, K8s catalog as SaaS, billing, dashboards, runbook integration.

## Architecture

Monorepo, additive. `backend/` (FastAPI + SQLAlchemy + Alembic, imports `fixdoc` package directly), `frontend/` (Next.js 14 App Router + Clerk + Tailwind reusing fixdoc-web palette), `src/fixdoc/cloud.py` + `commands/login.py` + `commands/team.py` on the CLI side. 7 Postgres tables: users, teams, team_members, projects, fixes (UNIQUE team_id + content_hash), pending_entries, api_keys, github_installations.

**Engine reuse:** `backend/app/services/*` are thin wrappers calling `fixdoc.change_impact.analyze_change_impact`, `fixdoc.k8s.engine.analyze_k8s_change`, `fixdoc.relevance.RelevanceMatcher`, `fixdoc.classifier.classify_entry`. Only storage differs (Postgres vs `~/.fixdoc/fixes.json`).

**GitHub App flow:** User installs app → adds `fixdoc/analyze-action@v1` step to existing Terraform workflow → action uploads plan JSON to `POST /analyze` → backend runs engine and posts PR comment via installation token, idempotent via `<!-- fixdoc-risk-analysis -->` marker. Customer runs terraform with their own creds; we only see plan JSON.

## 4-Week Build Plan

1. **Week 1 — Backend:** `backend/pyproject.toml`, `app/main.py`, `app/config.py`, `app/database.py`, `app/middleware/auth.py`, 7 SQLAlchemy models, Alembic migration, routers (health, auth, teams, fixes, pending), Railway Postgres deploy.
2. **Week 2 — Frontend:** `frontend/package.json`, `app/layout.tsx` with ClerkProvider, pages (dashboard, fixes list+detail, pending, settings + settings/team), `lib/api.ts` with Clerk token injection, Railway deploy at app.fixdoc.dev.
3. **Week 3 — CLI adapter:** `src/fixdoc/cloud.py` (CloudClient), `commands/login.py`, `commands/team.py` (push/pull/search/status), `CloudConfig` in config.py, optional cloud mirror in `FixRepository.save()`, tests.
4. **Week 4 — GitHub App:** `backend/app/integrations/github_app.py`, `routers/webhooks.py`, `routers/analyze.py`, frontend `settings/integrations` page, extract `_format_markdown` from `commands/analyze.py` to shared module, external `fixdoc/analyze-action` repo.

## Non-Goals (Phase 0)

Billing, SSO/SAML, per-project RBAC, audit logs, self-hosted option, multi-region, custom dashboards, websockets, cloud outcomes table, Obsidian/Slack/runbook integrations, centralized AI.

## Verification

`curl /health` → 200, signup flow via Clerk → create team → generate API key → `fixdoc login` → `fixdoc team push` → second machine `fixdoc team pull` finds fixes → GitHub App installed → Terraform PR → comment posted → second push updates in place → `pytest` all 1328 existing tests pass unchanged → Railway deploy.

## Files

**New:** `backend/` tree, `frontend/` tree, `src/fixdoc/cloud.py`, `src/fixdoc/commands/login.py`, `src/fixdoc/commands/team.py`, `tests/test_cloud.py`, `tests/test_team_commands.py`.

**Modified:** `railway.toml` (2 services + Postgres addon), `src/fixdoc/cli.py` (register login/team), `src/fixdoc/commands/__init__.py`, `src/fixdoc/config.py` (CloudConfig), `src/fixdoc/storage.py` (optional cloud_client kwarg), `src/fixdoc/change_impact.py` or new `change_impact_format.py` (extract `_format_markdown` for backend reuse).

**Success criteria:** (1) New user signup → PR comment in 10 min, (2) cross-machine fix sharing works, (3) 1328 existing tests pass, (4) marketing site has "Sign in" → app.fixdoc.dev, (5) zero engine duplication between CLI and backend.
