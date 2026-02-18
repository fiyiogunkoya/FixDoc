# FixDoc

Stop losing infrastructure fixes in Slack threads — capture, search, and share them from your terminal.

## See It In Action

```bash
# Pipe errors directly from any command
terraform apply 2>&1 | fixdoc capture

# Or wrap the command — auto-captures on failure
fixdoc watch -- terraform apply

# Search your fix history
fixdoc search "S3 access denied"
```

```
[1] S3 bucket policy denied public access block (2024-11-03)
    Tags: aws, s3, iam
    Resolution: Add explicit s3:GetObject allow for the deployment role ARN

[2] AccessDenied on S3 presigned URL — wrong region endpoint (2024-10-21)
    Tags: aws, s3
    Resolution: Switch client to us-east-1; presigned URLs are region-scoped
```

## What It Does

**Core workflow:**
- Pipe or wrap any command — auto-detects Terraform/Kubernetes errors and prompts for your resolution
- Surfaces similar fixes from your history before creating duplicates
- Stores everything as searchable JSON + markdown in `~/.fixdoc/`

**Team and CI features:**
- Sync fixes with your team via a shared Git repo
- Analyze Terraform plans against your fix history before `apply`
- Gate CI pipelines on blast radius severity (`--exit-on high`)

## Installation

```bash
pip install fixdoc
```

Requires Python 3.9+. Only runtime dependencies are `click` and `pyyaml`.

## How It Works

Source-specific parsers (Terraform, Kubernetes, and a generic fallback) extract structured metadata from error output — provider, resource type, error code — so fixes are queryable, not just searchable. Everything persists as structured JSON plus a human-readable markdown file, so your fix database is both machine-queryable and readable in any editor or GitHub repo. The blast radius command traverses your Terraform dependency graph and scores the potential impact of a plan against your fix history, giving you a severity signal before `apply`.

## Contributing

```bash
git clone https://github.com/fiyiogunkoya/fixdoc.git
cd fixdoc
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run `pytest` (372 tests). Format with `black src/ tests/` and lint with `ruff check src/ tests/`.

Good places to start: new error parsers live in `src/fixdoc/parsers/` and share a common interface; new CLI commands are self-contained files in `src/fixdoc/commands/`; the GitHub Actions integration is at `.github/workflows/terraform-risk-analysis.yml`.

## License

MIT
