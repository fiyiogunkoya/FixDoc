# fixdoc/analyze-action

GitHub Action that runs FixDoc change impact analysis on Terraform plans and posts the result as a PR comment.

Keeps `terraform plan` on your runner (with your cloud creds); only the plan JSON is sent to FixDoc.

## Usage

```yaml
jobs:
  risk:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform init
      - run: terraform plan -out=tf.plan
      - run: terraform show -json tf.plan > plan.json
      - uses: fixdoc/analyze-action@v1
        with:
          plan: plan.json
          api-key: ${{ secrets.FIXDOC_API_KEY }}
          # Optional: fail the job on high-risk PRs
          fail-on: high
```

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `plan` | yes | — | Path to `terraform show -json` output |
| `api-key` | yes | — | Generate at [app.fixdoc.dev/settings](https://app.fixdoc.dev/settings) |
| `api-url` | no | `https://api.fixdoc.dev` | Override for self-hosted |
| `installation-id` | no | auto | GitHub App installation ID (auto-detected from `github.event.installation.id`) |
| `fail-on` | no | `never` | `low` / `medium` / `high` / `critical` / `never` |

## What it does

1. Loads the plan JSON you produced on your runner
2. POSTs to `$FIXDOC_API_URL/api/v1/analyze` with the plan and PR context
3. Backend runs the change impact engine against your team's fix database
4. Backend posts a risk comment on the PR (idempotent — updates in place)
5. Job summary gets the same markdown so it's visible in the Actions tab

## Required scopes

Install the FixDoc GitHub App on your repo (one-click from the web UI) — it requests:
- `contents: read`
- `pull_requests: write`

No repo secrets beyond `FIXDOC_API_KEY` are needed.
