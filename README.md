# FixDoc

A CLI tool for cloud engineers to capture and search infrastructure fixes. Stop losing tribal knowledge in Slack threads and personal notes.

## The Problem

Infrastructure errors repeat. The same S3 bucket naming collision, the same Kubernetes CrashLoopBackOff, the same Terraform state lock — solved six months ago, but the fix is buried in Slack or locked in someone's head. When engineers leave, the knowledge leaves with them. Teams waste hours re-debugging problems they've already solved.

## What FixDoc Does

Pipe your Terraform or kubectl error output directly into FixDoc. It auto-detects the error source, extracts the provider, resource type, file, line number, and error code, then prompts you for the resolution. Next time you or a teammate hits a similar issue, search your fix history instead of starting from scratch.

```bash
terraform apply 2>&1 | fixdoc capture
```

```
──────────────────────────────────────────────────
Captured from Terraform:

  Provider: AWS
  Resource: aws_s3_bucket.data
  File:     storage.tf:12
  Code:     BucketAlreadyExists
  Error:    BucketAlreadyExists: error creating S3 Bucket...

  Suggestions:
    - S3 bucket names are globally unique. Use a different name
    - Add a random suffix to the bucket name
──────────────────────────────────────────────────

 What fixed this?: Added account ID suffix to bucket name
 Tags [comma-separated]: terraform,aws,s3

Fix captured: a1b2c3d4
```

Then later:

```bash
$ fixdoc search "S3"
  [a1b2c3d4] Terraform AWS: S3 BucketAlreadyExists  (terraform,aws,s3)
```

## Features

- **Pipe errors directly** from `terraform apply` or `kubectl` — no copy-pasting
- **Auto-parse errors** from Terraform (AWS, Azure, GCP) and Kubernetes
- **Similar fix suggestions** — shows matching fixes from your history before creating duplicates
- **Search your fix history** by keyword, tag, or error message
- **Watch mode** — wrap any command and auto-capture errors on failure
- **Blast radius analysis** — estimate the impact of Terraform changes before applying
- **Analyze Terraform plans** against your fix history before `apply`
- **CI gating** — fail pipelines when blast radius severity exceeds a threshold
- **Sync with your team** via a shared Git repo
- **Markdown export** — every fix generates a shareable `.md` file

## Try It Now (Demo)

You don't need a live cloud environment to try FixDoc. The built-in demo walks you through the real capture pipeline with sample errors:

```bash
pip install fixdoc
fixdoc demo tour
```

The tour walks you through 5 steps:

1. **Capture a Terraform error**: A sample `BucketAlreadyExists` error is piped through the parser. You see the auto-extracted provider, resource, file, and error code, then type a resolution.
2. **Capture a Kubernetes error**: A `CrashLoopBackOff` error goes through the same pipeline, extracting the pod name, namespace, restart count, and status.
3. **Search**: Searches your database for "S3" and shows matching fixes.
4. **List and stats**: Shows all stored fixes and tag frequency.
5. **Analyze a Terraform plan**: A sample plan JSON with 3 resources is analyzed against your fix history, flagging resources that have caused issues before.

Fixes captured during the tour are real entries saved to your local database, so you can explore them afterwards with `fixdoc list`, `fixdoc show`, and `fixdoc search`.

You can also seed sample data without the interactive walkthrough:

```bash
fixdoc demo seed          # Add 6 realistic sample fixes
fixdoc demo seed --clean  # Remove old demo data first
```

## Installation

**From PyPI (recommended):**

```bash
pip install fixdoc
```

**From source (for development):**

```bash
git clone https://github.com/fiyiogunkoya/fixdoc.git
cd fixdoc
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.9+.

## Usage

### Capture a Fix

**Pipe from Terraform:**
```bash
terraform apply 2>&1 | fixdoc capture
```

**Pipe from kubectl:**
```bash
kubectl apply -f deployment.yaml 2>&1 | fixdoc capture
```

**Interactive mode:**
```bash
fixdoc capture
```

**Quick one-liner:**
```bash
fixdoc capture -q "S3 bucket name collision | Added account ID suffix" -t terraform,aws,s3
```

### Watch Mode

Wrap any command with `fixdoc watch`. It streams output to your terminal in real-time and, if the command fails, offers to capture the error through the fixdoc pipeline:

```bash
fixdoc watch -- terraform apply
fixdoc watch -- kubectl apply -f deployment.yaml
```

Options:
- `--tags/-t` — pre-set tags on the captured fix
- `--no-prompt` — skip the confirmation prompt and capture automatically on failure

```bash
# Auto-capture with tags, no confirmation
fixdoc watch -t terraform,aws --no-prompt -- terraform apply
```

The wrapped command's exit code is always preserved, so `fixdoc watch` is safe to use in scripts and CI.

### Deferred Errors (Pending)

During watch mode, errors can be deferred instead of captured immediately. Deferred errors are
stored in `.fixdoc-pending` at your git root, so you can come back to them later.

```bash
fixdoc pending                   # List all deferred errors
fixdoc pending capture <id>      # Capture a deferred error (use ID or list number)
fixdoc pending remove <id>       # Remove a single deferred error
fixdoc pending clear             # Remove all deferred errors
```

Example: defer an error during `watch`, then capture it after the incident:

```bash
# During watch — choose "defer" when prompted
fixdoc watch -- terraform apply

# Later, when you have time
fixdoc pending               # See what's waiting
fixdoc pending capture 1     # Capture error #1 from the list
```

> **Note:** `.fixdoc-pending` is local to your workspace. Add it to your project's `.gitignore`.

### Search

```bash
fixdoc search "bucket"
fixdoc search rbac
fixdoc search "CrashLoopBackOff"
```

### Blast Radius Analysis

Estimate which resources are affected by infrastructure changes before applying them. FixDoc analyzes your Terraform plan JSON, identifies high-criticality control points (IAM roles, security groups, network resources), traces the dependency graph to find affected downstream resources, and cross-references your fix history to flag resources that have caused problems before.

```bash
# Generate the plan JSON
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json

# Run blast radius analysis
fixdoc analyze plan.json
```

```
Blast Radius Analysis
=====================
Score: 62 / 100  [HIGH]

Changed Control Points (2):
  UPDATE  aws_iam_role.lambda_exec                [iam, criticality: 0.9]
  CREATE  aws_security_group_rule.allow_https      [network, criticality: 0.8]

Affected Resources (4):
  aws_lambda_function.api                    (depth: 1, via: aws_iam_role.lambda_exec)
  aws_api_gateway_integration.proxy          (depth: 2, via: aws_lambda_function.api)
  aws_instance.web                           (depth: 1, via: aws_security_group_rule.allow_https)
  aws_lb_target_group.web                    (depth: 2, via: aws_instance.web)

Fix History Matches (1):
  FIX-a1b2c3d4: Lambda timeout after IAM role policy change

Recommended Checks:
  - Review IAM policy changes for least-privilege compliance
  - Verify security group rules don't expose unintended ports

Summary: 5 changes, 2 control points, 4 affected resources
```

**Options:**

| Flag | Description |
|------|-------------|
| `--graph/-g <file>` | Path to a DOT file from `terraform graph`. Auto-runs if terraform is on PATH. |
| `--format/-f <fmt>` | Output format: `human` (default) or `json` |
| `--max-depth/-d <n>` | Max BFS traversal depth for dependency propagation (default: 5) |
| `--exit-on <level>` | Exit with code 1 if severity meets or exceeds `low`, `medium`, `high`, or `critical`. For CI gating. |

**With a dependency graph:**
```bash
terraform graph > graph.dot
fixdoc analyze plan.json --graph graph.dot
```

**JSON output for scripting:**
```bash
fixdoc analyze plan.json --format json
```

**CI gating — fail the pipeline if severity is high or above:**
```bash
fixdoc analyze plan.json --exit-on high
```

### CI Integration

FixDoc includes a GitHub Actions workflow for automatic risk analysis on Terraform pull requests. Add `.github/workflows/terraform-risk-analysis.yml` to your repo:

```yaml
name: Terraform Risk Analysis

on:
  pull_request:
    paths:
      - "**/*.tf"
      - "**/*.tfvars"

jobs:
  risk-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - name: Install fixdoc
        run: pip install fixdoc
      - name: Terraform Init
        run: terraform init
      - name: Terraform Plan
        run: terraform plan -out=plan.tfplan
      - name: Analyze Risk
        run: |
          terraform show -json plan.tfplan > plan.json
          fixdoc analyze plan.json --exit-on high
```

This blocks PRs that introduce high or critical blast radius changes.

### Analyze Terraform Plans

Check a plan against your fix history before applying:

```bash
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json
```

```
Found 2 potential issue(s) based on your fix history:

X  aws_s3_bucket.app_data may relate to FIX-a1b2c3d4
   Previous issue: S3 BucketAlreadyExists
   Resolution: Added account ID suffix to bucket name
   Tags: terraform,aws,s3

X  aws_security_group.web_sg may relate to FIX-b5c6d7e8
   Previous issue: Security group rule conflict
   Resolution: Added lifecycle ignore_changes for ingress rules
   Tags: terraform,aws,security_group

Run `fixdoc show <fix-id>` for full details on any fix.
```

### Edit a Fix

```bash
fixdoc edit a1b2c3d4 --resolution "Updated fix details"
fixdoc edit a1b2c3d4 --tags "terraform,aws,s3,naming"
fixdoc edit a1b2c3d4 -I   # Interactive edit
```

### Team Sync via Git

Share fixes across your team through a shared Git repository:

```bash
fixdoc sync init git@github.com:your-org/team-fixes.git
fixdoc sync push -m "Added S3 naming fixes"
fixdoc sync pull
fixdoc sync status
```

Fixes marked as private (`is_private`) are excluded from sync.

### Other Commands

```bash
fixdoc list                    # List all fixes
fixdoc show a1b2c3d4           # Show full details of a fix
fixdoc stats                   # View fix statistics
fixdoc delete a1b2c3d4         # Delete a fix
fixdoc delete --purge          # Delete all fixes
```

## How It Works

### Parser Pipeline

When you pipe error output to `fixdoc capture`, the router auto-detects the error source (Terraform vs Kubernetes vs generic) using heuristics, then delegates to the appropriate parser. Parsers extract:

- **Terraform**: cloud provider, resource type, file + line number, error code, and generate fix suggestions
- **Kubernetes**: pod name, namespace, status, restart count, exit code

### Similar Fix Suggestions

When capturing a new error, FixDoc automatically searches your fix history for similar issues using a weighted scoring system. It matches on:

- **Tags** — shared tags between the new error and existing fixes
- **Error codes** — common error codes (HTTP status codes, cloud provider error names)
- **Keywords** — overlapping terms in the issue and resolution text
- **Resource types** — AWS, Azure, and GCP resource type prefixes

If similar fixes are found, you can select an existing one instead of creating a duplicate.

### Blast Radius Engine

The blast radius engine combines three signals to compute a risk score (0-100):

1. **Control point detection** — identifies IAM roles, security groups, network resources, and other high-criticality resources being changed, classified by category and criticality (0-1)
2. **Dependency propagation** — uses the `terraform graph` DAG to trace which downstream resources are affected via bounded BFS traversal
3. **Fix history prior** — cross-references changed resources against your fix database to flag resources that have caused problems before

The score maps to severity levels: low (0-25), medium (26-50), high (51-75), critical (76-100). Sensitive values in the plan are redacted before output.

### Storage

Everything is stored locally at `~/.fixdoc/`:

```
~/.fixdoc/
├── fixes.json      # JSON database of all fixes
├── config.yaml     # Sync and user configuration
└── docs/           # Generated markdown files
    ├── <uuid>.md
    └── ...
```

Set the `FIXDOC_HOME` environment variable to override the default storage location:

```bash
export FIXDOC_HOME=/path/to/custom/fixdoc
```

Each fix is a JSON object with these fields:

| Field | Required | Description |
|-------|----------|-------------|
| Issue | Yes | What was the problem? |
| Resolution | Yes | How did you fix it? |
| Error excerpt | No | Relevant error output or logs |
| Tags | No | Comma-separated keywords (resource types, categories) |
| Notes | No | Gotchas, context, misleading directions |

Use resource types as tags (e.g., `aws_s3_bucket`, `azurerm_key_vault`) to enable Terraform plan analysis and blast radius history matching.

### Git Sync

The sync system pushes markdown files to a shared repo. On pull, `fixdoc` parses them back into Fix objects and merges with local data. Conflict detection handles both-modified and deleted-on-one-side cases.

## Design Philosophy

**Speed is everything.** Engineers won't document fixes if it takes more than a few seconds. FixDoc is designed around this:

- Pipe errors directly; no manual copy-paste
- Auto-extract structured data from error output
- Watch mode for hands-free error capture
- Quick mode for one-liner captures
- Similar fix suggestions to avoid duplicate work
- Optional fields you can skip

The goal is to build a searchable knowledge base over time, not to write perfect documentation for every fix.

## Roadmap

| Feature | Description |
|---------|-------------|
| Import/Export | `fixdoc export` and `fixdoc import --merge` for portability |
| Search filters | Filter by tags, date range, provider |
| Additional parsers | AWS CLI, Azure CLI, Ansible error parsers |
| AI-suggested fixes | Suggest resolutions from error context + fix history |

## Development

### Setup

```bash
git clone https://github.com/fiyiogunkoya/fixdoc.git
cd fixdoc
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.9+.

### Running Tests

```bash
# All tests
pytest

# Single file
pytest tests/test_models.py

# With coverage
pytest --cov=fixdoc tests/

# Integration tests only
pytest tests/test_integration_terraform.py -v
```

Test count: 372 (348 unit + 24 integration). Use `python3`, not `python`.

### Code Style

```bash
black src/ tests/      # Format
ruff check src/ tests/ # Lint
```

### Architecture Overview

| Layer | Location | Purpose |
|-------|----------|---------|
| Entry point | `src/fixdoc/fix.py` → `cli.py` | Assembles Click commands |
| Commands | `src/fixdoc/commands/` | One file per CLI command |
| Engine | `src/fixdoc/blast_radius.py`, `pending.py`, `suggestions.py` | Core logic |
| Parsers | `src/fixdoc/parsers/` | Terraform / Kubernetes / generic error parsing |
| Storage | `src/fixdoc/storage.py` | JSON database + markdown files at `~/.fixdoc/` |
| Config | `src/fixdoc/config.py` | `~/.fixdoc/config.yaml` management |

### Adding a New Parser

1. Create `src/fixdoc/parsers/<name>.py` implementing `ErrorParser` from `base.py`
2. Register it in `src/fixdoc/parsers/router.py`

### Key Test Patterns

- Use `importlib.import_module("fixdoc.commands.<module>")` to get command modules for patching (avoids `__init__.py` export shadowing)
- For JSON CLI tests: `CliRunner(mix_stderr=False)` to separate stderr from stdout
- `PendingStore` in watch tests is lazily created — patch it separately for defer-path tests

### Contributing

Contributions are welcome. Please open an issue or PR. Run the full test suite before submitting:

```bash
pytest && ruff check src/ tests/ && black --check src/ tests/
```

## License

MIT
