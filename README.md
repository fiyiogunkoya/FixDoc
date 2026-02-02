# FixDoc

A CLI tool for cloud engineers to capture and search infrastructure fixes. Stop losing tribal knowledge in Slack threads and personal notes.

## The Problem

Infrastructure errors repeat. The same S3 bucket naming collision, the same Kubernetes CrashLoopBackOff, the same Terraform state lock, solved six months ago, but the fix is buried in Slack or locked in someone's head. When engineers leave, the knowledge leaves with them. Teams waste hours re-debugging problems they've already solved.

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
- **Search your fix history** by keyword, tag, or error message
- **Analyze Terraform plans** against your fix history before `apply`
- **Sync with your team** via a shared Git repo
- **Markdown export** -  every fix generates a shareable `.md` file

## Try It Now (Demo)

You don't need a live cloud environment to try FixDoc. The built-in demo walks you through the real capture pipeline with sample errors:

```bash
pip install fixdoc
fixdoc demo tour
```

The tour walks you through 5 steps:

1. **Capture a Terraform error** : A sample `BucketAlreadyExists` error is piped through the parser. You see the auto-extracted provider, resource, file, and error code, then type a resolution.
2. **Capture a Kubernetes error** : A `CrashLoopBackOff` error goes through the same pipeline, extracting the pod name, namespace, restart count, and status.
3. **Search** : Searches your database for "S3" and shows matching fixes.
4. **List and stats** : Shows all stored fixes and tag frequency.
5. **Analyze a Terraform plan** : A sample plan JSON with 3 resources is analyzed against your fix history, flagging resources that have caused issues before.

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

### Search

```bash
fixdoc search "bucket"
fixdoc search rbac
fixdoc search "CrashLoopBackOff"
```

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

Each fix is a JSON object with these fields:

| Field | Required | Description |
|-------|----------|-------------|
| Issue | Yes | What was the problem? |
| Resolution | Yes | How did you fix it? |
| Error excerpt | No | Relevant error output or logs |
| Tags | No | Comma-separated keywords (resource types, categories) |
| Notes | No | Gotchas, context, misleading directions |

Use resource types as tags (e.g., `aws_s3_bucket`, `azurerm_key_vault`) to enable Terraform plan analysis.

### Git Sync

The sync system pushes markdown files to a shared repo. On pull, `fixdoc` parses them back into Fix objects and merges with local data. Conflict detection handles both-modified and deleted-on-one-side cases.

## Design Philosophy

**Speed is everything.** Engineers won't document fixes if it takes more than a few seconds. FixDoc is designed around this:

- Pipe errors directly; no manual copy-paste
- Auto-extract structured data from error output
- Quick mode for one-liner captures
- Optional fields you can skip

The goal is to build a searchable knowledge base over time, not to write perfect documentation for every fix.

## Roadmap

| Feature | Description |
|---------|-------------|
| Similar fix suggestions | Show matching fixes before creating duplicates |
| Import/Export | `fixdoc export` and `fixdoc import --merge` for portability |
| Search filters | Filter by tags, date range, provider |
| Additional parsers | AWS CLI, Azure CLI, Ansible error parsers |
| AI-suggested fixes | Suggest resolutions from error context + fix history |

## Development

```bash
git clone https://github.com/fiyiogunkoya/fixdoc.git
cd fixdoc
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=fixdoc tests/

# Format
black src/ tests/

# Lint
ruff check src/ tests/
```

## Contributing

Contributions are welcome. Please open an issue or PR.

## License

MIT
