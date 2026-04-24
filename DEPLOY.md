# FixDoc Phase 0 Deployment

End-to-end walkthrough from cold start to first paying team. Takes ~60 minutes if every account is ready.

Three external accounts needed: **Clerk** (auth), **GitHub** (App registration), **Railway** (hosting — already in use for the marketing site). Domain (`fixdoc.dev` via Cloudflare) assumed from earlier conversation.

---

## Prereqs checklist

- [ ] Domain `fixdoc.dev` registered at Cloudflare (or wherever you bought it)
- [ ] Railway account with billing configured
- [ ] Clerk account created at [dashboard.clerk.com](https://dashboard.clerk.com)
- [ ] GitHub account (personal or org — must match where the App will be registered)
- [ ] Local clone of `fiyiogunkoya/FixDoc` with latest `main`

---

## Step 1 — Clerk setup (5 min)

1. Go to [dashboard.clerk.com](https://dashboard.clerk.com) → **Create application**
2. Name: `FixDoc` · Sign-in options: **Email** + **Google** (enable both)
3. Copy the following from **API Keys**:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (pk_live_…)
   - `CLERK_SECRET_KEY` (sk_live_…)
4. Get your Clerk **Frontend API URL** from **Domains** → it looks like `https://clerk.fixdoc.dev` once custom domain is set, or `https://<slug>.clerk.accounts.dev` during testing
5. JWKS URL = `${FRONTEND_API}/.well-known/jwks.json` — save for backend env
6. **Webhooks** → **+ Add Endpoint** (do this *after* backend is deployed; leave a placeholder)

---

## Step 2 — Railway: provision services (15 min)

All three services live in the same Railway project so they share the Postgres addon and can use `${{backend.RAILWAY_PUBLIC_DOMAIN}}` style references.

### 2a. Link the existing project

```bash
railway login                    # opens browser, authenticates CLI
railway link                     # pick your existing fixdoc-web project
```

### 2b. Add the Postgres addon

Dashboard → **+ New** → **Database** → **PostgreSQL**. Railway exposes a `DATABASE_URL` variable automatically.

### 2c. Add the **backend** service

Dashboard → **+ New** → **GitHub Repo** → pick `FixDoc`. Once the service appears:
- **Settings → General → Service Name:** `backend`
- **Settings → Source → Root Directory:** `backend`

Railway reads `backend/railway.toml` (already in the repo) which points at `backend/Dockerfile`. The Dockerfile pulls the `fixdoc` library directly from GitHub (pinned to the `k8s` branch via the `FIXDOC_GIT_REF` build arg), so the build context stays service-local — no need for any monorepo path config.

Then under **Variables**, add:

```
FIXDOC_ENVIRONMENT=production
FIXDOC_DEBUG=false
FIXDOC_DATABASE_URL=${{Postgres.DATABASE_URL}}?sslmode=require
FIXDOC_CLERK_SECRET_KEY=sk_live_xxx
FIXDOC_CLERK_PUBLISHABLE_KEY=pk_live_xxx
FIXDOC_CLERK_JWKS_URL=https://<your-clerk-frontend>.clerk.accounts.dev/.well-known/jwks.json
FIXDOC_CLERK_WEBHOOK_SECRET=whsec_placeholder
FIXDOC_CORS_ORIGINS=["https://app.fixdoc.dev"]
# GitHub App — leave empty for now; fill after Step 4
FIXDOC_GITHUB_APP_ID=
FIXDOC_GITHUB_APP_PRIVATE_KEY=
FIXDOC_GITHUB_APP_SLUG=
FIXDOC_GITHUB_WEBHOOK_SECRET=
```

Deploy. Watch logs — you should see Alembic apply `0001_initial_schema` then uvicorn start.

Verify:
```bash
curl https://<backend>.up.railway.app/health          # → {"status":"ok"}
```

### 2d. Add the **frontend** service

Same flow. Add another GitHub Repo service → same `FixDoc` repo → then:
- **Settings → General → Service Name:** `frontend`
- **Settings → Source → Root Directory:** `frontend`

Railway reads `frontend/railway.toml` which points at `frontend/Dockerfile`. Build context is `frontend/` — self-contained.

Variables:
```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_xxx
CLERK_SECRET_KEY=sk_live_xxx
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard
FIXDOC_API_URL=${{backend.RAILWAY_PRIVATE_DOMAIN}}
NEXT_PUBLIC_FIXDOC_GITHUB_APP_SLUG=fixdoc
```

(Using `RAILWAY_PRIVATE_DOMAIN` keeps backend traffic on the internal mesh — no public Internet hop for the proxy rewrites.)

Deploy. Verify:
```bash
curl https://<frontend>.up.railway.app             # returns Next.js HTML
```

---

## Step 3 — Custom domains (10 min)

In Cloudflare DNS:

| Type  | Name  | Target                                    | Proxy |
|-------|-------|-------------------------------------------|-------|
| CNAME | `api` | `<backend>.up.railway.app`                | DNS only (gray cloud) |
| CNAME | `app` | `<frontend>.up.railway.app`               | DNS only (gray cloud) |

In Railway dashboard → backend service → **Settings** → **Networking** → **+ Custom Domain** → `api.fixdoc.dev`. Repeat for frontend with `app.fixdoc.dev`.

Cert issuance is automatic (Let's Encrypt); takes ~2 minutes once DNS resolves.

Once live, update the backend variable:
```
FIXDOC_CORS_ORIGINS=["https://app.fixdoc.dev"]
```
and the frontend variable:
```
FIXDOC_API_URL=https://api.fixdoc.dev
```

---

## Step 4 — GitHub App registration (10 min)

1. Go to [github.com/settings/apps](https://github.com/settings/apps) → **New GitHub App**
   (Organization owners: use `github.com/organizations/<org>/settings/apps/new`)
2. Fill in:
   - **App name:** `FixDoc` (must be unique — if taken, try `fixdoc-ci` or similar; set the slug as `FIXDOC_GITHUB_APP_SLUG`)
   - **Homepage URL:** `https://fixdoc.dev`
   - **Callback URL:** `https://app.fixdoc.dev/settings/integrations`
   - **Setup URL (optional):** same as callback
   - **Webhook URL:** `https://api.fixdoc.dev/webhooks/github`
   - **Webhook secret:** generate with `openssl rand -hex 32` — save for backend env
   - **Permissions:**
     - Repository → **Contents**: Read
     - Repository → **Pull requests**: Read & write
     - Repository → **Metadata**: Read (auto-selected)
   - **Subscribe to events:** `Installation`, `Installation repositories`
   - **Where can this app be installed?** Any account
3. **Create GitHub App**
4. Copy the **App ID** from the top of the page
5. **Generate a private key** — downloads `.pem` file. Open it, copy the entire contents (BEGIN to END).
6. Back in Railway → backend service → update variables:
   ```
   FIXDOC_GITHUB_APP_ID=<App ID number>
   FIXDOC_GITHUB_APP_PRIVATE_KEY=<paste entire PEM, including BEGIN/END lines>
   FIXDOC_GITHUB_APP_SLUG=<slug from URL, e.g. "fixdoc" or "fixdoc-ci">
   FIXDOC_GITHUB_WEBHOOK_SECRET=<secret from step 2>
   ```
7. Frontend service: update `NEXT_PUBLIC_FIXDOC_GITHUB_APP_SLUG` to match

Backend redeploys automatically on variable change.

Smoke test the webhook: GitHub dashboard → your App → **Advanced** → **Recent Deliveries** → send a ping. Should return 204.

---

## Step 5 — Clerk webhook (3 min)

Back in Clerk dashboard → **Webhooks** → **+ Add Endpoint**:
- **Endpoint URL:** `https://api.fixdoc.dev/webhooks/clerk`
- **Subscribe to events:** `user.created`, `user.updated`, `user.deleted`
- Copy the **Signing Secret** → set `FIXDOC_CLERK_WEBHOOK_SECRET=whsec_…` in Railway backend

Redeploy. Test: sign up a new user in Clerk → check backend logs for the webhook hit → verify the user row appears in Postgres:

```bash
railway connect Postgres
psql=> select clerk_user_id, email from users;
```

---

## Step 6 — First end-to-end smoke (5 min)

1. Browse to `https://app.fixdoc.dev` → sign up with your real email
2. The dashboard loads but is empty — **create a team** via
   ```bash
   curl -X POST https://api.fixdoc.dev/api/v1/teams \
     -H "Authorization: Bearer $(pbpaste)" \
     -H "Content-Type: application/json" \
     -d '{"name":"Personal","slug":"personal"}'
   ```
   (Grab the Clerk JWT from the browser's DevTools → Application → Cookies → `__session`. Phase 1 adds a "Create team" UI.)
3. Refresh the dashboard — sidebar shows the team.
4. Settings → **Generate API key** → copy the `fd_live_…` token.
5. In a terminal:
   ```bash
   fixdoc login --api-url https://api.fixdoc.dev --token fd_live_xxx
   fixdoc capture   # or paste a prior error
   fixdoc team push
   ```
6. Browse back to `/fixes` — your push is visible.
7. Install the FixDoc GitHub App on a test repo → browser returns to `/settings/integrations` → installation appears linked.
8. Add the composite action to the repo's Terraform workflow:
   ```yaml
   - uses: fixdoc/analyze-action@v1
     with:
       plan: plan.json
       api-key: ${{ secrets.FIXDOC_API_KEY }}
   ```
9. Open a PR that touches `*.tf` → CI runs → the FixDoc risk comment appears on the PR.

If all 9 steps pass, Phase 0 is live.

---

## Rollback notes

- **Bad backend deploy?** Railway keeps the last N images — roll back via dashboard → backend → **Deployments** → **Revert**.
- **Bad migration?** Railway shell into the service and run `alembic downgrade -1`. Until Alembic has a `0002`, this drops everything.
- **Data disaster?** Railway's managed Postgres has daily snapshots; restore from dashboard → Postgres → **Backups**.

---

## What's next (Phase 1 triggers)

- When first team asks about billing → ship Stripe (Phase 2b, ~1 week)
- When someone asks "can I connect Slack?" → ship the Slack App (Phase 1b, ~1 week)
- When a user pastes an Obsidian folder path expecting it to work → ship the Obsidian importer (Phase 1a, ~3 days)
- When the Anthropic key on a CI runner gets rate-limited → ship centralized AI (Phase 1c, ~1 week)
