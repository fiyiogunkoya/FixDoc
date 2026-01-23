# FixDoc

A CLI tool for cloud engineers to capture and search infrastructure fixes. Stop losing tribal knowledge in Slack threads and personal notes.

## The Problem

Infrastructure errors repeat. The same RBAC misconfiguration, the same Terraform state lock—solved six months ago, but the fix is buried in Slack or locked in someone's head. When engineers leave, the knowledge leaves with them. Teams waste hours debugging problems they've already solved.

## The Solution

FixDoc captures cloud fixes in seconds and makes them searchable. Pipe your Terraform error output directly to FixDoc, document what fixed it, and move on. Next time you—or a teammate—hit a similar issue, search your fix history instead of debugging from scratch.

**Core features:**

- **Capture fixes fast** - Quick mode for one-liner captures, pipe terraform errors directly
- **Search your history** - Find past fixes by keyword, tag, or error message
- **Analyze terraform plans** - Get warnings about resources that have caused problems before
- **Markdown export** - Every fix generates shareable documentation

## Installation

```bash
# Clone the repo
git clone https://github.com/fiyiogunkoya/fixdoc.git
cd fixdoc

# Recommended: set up a virtual environment
python -m venv venv
source venv/bin/activate 

# Install 
pip install -e .
```

## Quick Start

### Capture a Fix

**Pipe terraform errors directly:**
```bash
terraform apply 2>&1 | fixdoc capture
```

FixDoc parses the error, extracts the resource and error code, and prompts you only for the fix:

```
──────────────────────────────────────────────────
Captured from terraform:

  Resource: azurerm_databricks_workspace.main
  File:     modules/databricks/main.tf:15
  Error:    KeyVaultAccessDenied: The operation does not have permission...
──────────────────────────────────────────────────

What fixed it? > Added managed identity to Key Vault access policy

Fix captured: a1b2c3d4(unique fix id)
```

**Interactive mode:**
```bash
fixdoc capture
```

**Quick mode:**
```bash
fixdoc capture -q "User couldn't access storage | Added blob contributor role" -t storage,rbac
```

### Search Your Fixes

```bash
fixdoc search "storage account"
fixdoc search rbac
fixdoc search "access denied"
```

### Edit a Fix

```bash
# Update specific fields
fixdoc edit a1b2c3d4 --resolution "Updated fix details"
fixdoc edit a1b2c3d4 --tags "storage,rbac,new_tag"

# Interactive edit
fixdoc edit a1b2c3d4 -I
```

### Analyze Terraform Plans

Before running `terraform apply`, check for known issues:

```bash
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json
```

Output:
```
Found 2 potential issue(s) based on your fix history:

X  azurerm_storage_account.main may relate to FIX-a1b2c3d4
   Previous issue: Users couldn't access blob storage
   Resolution: Added storage blob data contributor role
   Tags: azurerm_storage_account,rbac

X  azurerm_key_vault.main may relate to FIX-b5c6d7e8
   Previous issue: Key Vault access denied for Databricks
   Resolution: Added access policy with wrapKey permission
   Tags: azurerm_key_vault,rbac

Run `fixdoc show <fix-id>` for full details on any fix.
```

### Other Commands

```bash
fixdoc list                    # List all fixes
fixdoc show a1b2c3d4           # Show full details
fixdoc delete a1b2c3d4         # Delete a fix
fixdoc delete --purge          # Delete all fixes
fixdoc stats                   # View statistics
```

## Fix Fields

| Field | Required | Description |
|-------|----------|-------------|
| Issue | Yes | What was the problem? |
| Resolution | Yes | How did you fix it? |
| Error excerpt | No | Relevant error message or logs |
| Tags | No | Comma-separated keywords (resource types, categories) |
| Notes | No | Gotchas, misleading directions, additional context |

**Tip**: Use resource types as tags (e.g., `azurerm_storage_account`, `azurerm_key_vault`) to enable terraform plan analysis.

## Storage

FixDoc stores everything locally, I will eventually move to cloud storage:

```
~/.fixdoc/
├── fixes.json      # JSON database of all fixes
└── docs/           # Generated markdown files
    ├── <uuid>.md
    └── ...
```

Markdown files are generated alongside the JSON database, so you can:
- Push them to a wiki/confluence
- Commit them to a repo
- Share them with your team

## Philosophy

**Speed is everything.** Engineers won't document fixes if it takes too long. FixDoc is designed to capture information in seconds:

- Pipe errors directly from terraform
- Quick mode for one-liner captures
- Auto-extract resource, file, and error code
- Optional fields you can skip

The goal is to build a searchable knowledge base over time, not to write perfect documentation for each fix.

---

## Roadmap for next couple of weeks

### Week 1: Core Features & PyPI Release

| Feature | Description |
|---------|-------------|
| Similar fix suggestions | Show matching fixes before creating duplicates |
| Import/Export | `fixdoc export` and `fixdoc import --merge` |
| Search filters | Filter by tags, date range |
| Git context | Auto-capture repo, branch, commit |
| Multi-cloud parsing | kubectl, AWS CLI, Azure CLI error parsers |
| **PyPI publish** | `pip install fixdoc` |

### Week 2: AI Integration & SDK

| Feature | Description |
|---------|-------------|
| AI module | Support for Anthropic/OpenAI APIs |
| AI-suggested fixes | `fixdoc capture --ai` suggests resolution from error + history |
| Config system | `~/.fixdoc/config.yaml` for API keys and preferences |
| SDK refactor | Use as library: `from fixdoc import FixDoc` |

```python
from fixdoc import FixDoc

fd = FixDoc()
fd.capture(issue="...", resolution="...", tags=["storage"])
results = fd.search("rbac")
suggestion = fd.suggest(error="KeyVaultAccessDenied")
```

### Week 3: Web UI & API

| Feature | Description |
|---------|-------------|
| REST API | FastAPI backend: `/fixes`, `/search`, `/capture`, `/suggest` |
| Web dashboard | List, search, view, and capture fixes |
| AI in UI | "Suggest fix" button, semantic search |
| Deploy | Docker compose, cloud deployment |



### Future

- **Semantic search** - Find fixes by meaning, not just keywords
- **Team sync** - Central repository, shared across org
- **CI/CD integration** - GitHub Actions, Azure Pipelines
- **Pre-commit hooks** - Block commits with known issues
- **VS Code extension** - Inline warnings on .tf files

---

## Current Status

**v0.2.0 (current)**

What works today:
- Capture fixes (interactive, quick mode, piped terraform errors)
- Auto-parse terraform apply output (resource, file, line, error code)
- Search fixes by keyword
- Edit existing fixes
- Analyze terraform plans against fix history
- Delete individual fixes or purge all
- Store as JSON + markdown

---

## Contributing

Contributions welcome! Please open an issue or PR.