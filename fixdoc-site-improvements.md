# FixDoc Website Improvements (Actionable Checklist)

This doc consolidates all recommended improvements and additions for the FixDoc marketing site to increase conversion, trust, and activation—based on the screenshots you shared and your product direction (CI integration + fix-history warnings + proactive risk warnings + Blast Radius).

---

## Goals

1. **Reduce time-to-aha to < 30 seconds**
2. **Increase trust** (safe-by-default, local-first, clear privacy stance)
3. **Make the product feel real** (show shipped features, label previews)
4. **Create a distribution loop** (CI snippets + PR output = shareable)
5. **Position Blast Radius correctly** (Impact Preview now, deeper later)

---

## High-Impact Changes (Do These First)

### 1) Put “Install + First Win” above the fold
**Why:** Most devtool landing pages lose users because the first actionable step is too far down the page.

**Add directly under hero CTAs:**
```bash
pipx install fixdoc
fixdoc demo tour
```

**If you want an even faster one-liner:**
```bash
pipx install fixdoc && fixdoc demo tour
```

**Notes**
- Keep `pip install fixdoc` as an option, but make **pipx** the recommended path for a CLI.
- Add a copy button for the command block.

---

### 2) Make one CTA the obvious primary
Right now you have multiple competing CTAs (“Try the Demo”, “Get Started – It’s Free”, navbar “Get Started”).

**Recommended**
- Primary: **Run the Demo**
- Secondary: **View on GitHub** (or “Docs / Install”)

**Rule:** a user should never pause to decide what button to click.

---

### 3) Add a one-line “Trust & Privacy” callout near the hero
**Why:** devs hesitate to pipe logs into tools unless you explicitly address safety.

Add a short line (near the hero or immediately below the install snippet):

> Local-first by default. Stores fixes in `~/.fixdoc`. Git sync is optional. Private fixes never sync.

Optional second line:

> Redaction supported (tokens/keys masked before saving).

---

### 4) Make `watch` the default story (not piping)
Piping is powerful, but it feels like “extra work.” `watch` feels like a habit.

Update one of the hero/feature code cards to show:

```bash
fixdoc watch -- terraform apply
```

…and below it:

```bash
fixdoc search "access denied"
fixdoc analyze plan.json
```

---

### 5) Add a CI section with a copy-paste snippet (must-have for your roadmap)
Because your direction is CI integration + proactive warnings, the landing page should show this explicitly.

Add a section: **“Works in CI”** with:

- A minimal GitHub Actions example
- What the output looks like (job summary / PR comment)

Even if CI integration is “early,” showing it builds credibility and signals your “why” clearly.

---

## Blast Radius / Impact Preview: How to Present It on the Site

### 6) Label Blast Radius honestly (Preview vs Shipped)
Your Blast Radius animation is strong visually, but **it can backfire** if users think it’s marketing-only.

**If not shipped yet:**
- Add a badge: `Preview` / `In Progress`
- Add a line beneath the animation:
  > “Coming soon: Impact Preview from Terraform plan JSON + your fix history.”

**If partially shipped:**
- Add a CLI output snippet beside/under the animation:

```bash
fixdoc analyze plan.json --impact
# 1 change, 7 impacted (depth 2). Risk: HIGH (rbac)
# Related fixes: FIX-a1b2c3d4, FIX-b5c6d7e8
```

### 7) Rename (optional): “Blast Radius” → “Impact Preview”
“Blast radius” is memorable, but “Impact Preview” reads more like a developer tool and less like marketing.

You can still keep “Blast Radius” in copy:
- Header: **Impact Preview**
- Subheader: “See your blast radius before apply.”

---

## Page Structure Improvements (Information Architecture)

### 8) Add a “60-second demo” section earlier on the page
Right now, the install demo block is near the bottom. Move it up.

Recommended 3-step flow:

1. Install
2. Run demo
3. Try on your own plan

Example:

```bash
pipx install fixdoc
fixdoc demo tour
terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json --impact
```

---

### 9) Add “Real Outputs” (screenshots/GIFs) for each key feature
For each of these, show a small output snippet:

- Capture (watch + pipe)
- Search
- Analyze (fix match)
- Impact Preview (blast radius lite)
- Git sync (push/pull/status)

This makes FixDoc feel “already usable,” not conceptual.

---

### 10) Add “Who it’s for” + “Not another tool” contrast (small section)
Add a simple contrast block:

**FixDoc is NOT**
- an incident management SaaS
- a full-service catalog portal
- a generic doc tool

**FixDoc IS**
- terminal-first fix capture
- searchable fix history
- proactive plan/CI warnings based on your team’s scars

---

## Copy Improvements (Specific Suggestions)

### 11) Tighten the hero subhead to include CI (your differentiator)
Current hero is strong; the subhead can be more concrete.

Suggested subhead:

> Capture, search, and share Terraform & Kubernetes fixes—then warn in CI when a change matches something your team already fixed.

---

### 12) Add “How it works” in 3 bullets (no more)
Immediately after hero (or after install snippet):

- **Capture** fixes automatically with `watch` or via piped output
- **Search** your fix history by keyword, tags, or error excerpt
- **Analyze** Terraform plans to flag repeat issues + Impact Preview (blast radius)

---

## UX / Product Messaging Enhancements

### 13) Add a “Safety” mini-section
A small section that answers objections:

- What data is stored?
- Where is it stored?
- Does FixDoc send anything to the cloud?
- How does Git sync work?
- How are private fixes handled?

Even 4 bullets is enough.

---

### 14) Add a “Roadmap” teaser (but keep it short)
Show 3 items, not 12.

Example:
- Similar-fix suggestions during capture
- Impact Preview (blast radius)
- CI integration + PR comments

---

## Homepage CTA Section (Bottom of Page)

### 15) Make the bottom code block match the above-the-fold snippet
Right now the bottom section shows `pip install fixdoc`. Update to:

```bash
pipx install fixdoc
fixdoc demo tour
```

Then provide the pip fallback underneath:

```bash
pip install fixdoc
```

---

## “Crickets” Fix: Distribution & Launch Assets to Add to the Site

### 16) Add a “Launch pack” section for social proof (even small)
- Link to PyPI
- Link to GitHub
- Short changelog link (“What’s new”)

Even if you don’t have logos yet, these links help.

---

### 17) Add a dedicated “Demo” page that is copy-paste friendly
Your nav includes “Demo.” Make that page extremely simple:

- One install command
- One demo command
- One “try on your plan” command
- A GIF

No extra text.

---

## Blast Radius / Impact Preview MVP Definition (for alignment)

### 18) Ship “Blast Radius Lite” as part of `analyze`
Don’t create a separate command initially. Add flags:

- `fixdoc analyze plan.json --impact`
- `--depth 2` (default)
- `--format json` (for CI)
- `--risk-threshold high` (optional)
- `--exit 1` (optional for gating)

Output should include:
- Changed resources (L0)
- Impacted dependents (L1/L2)
- Risk score + reasons (RBAC/network/key mgmt/replace)
- Related fixes from history (matches)

---

## Implementation Notes (Site + Product Alignment)

### 19) Avoid over-promising “architecture-level comms” in MVP
Present Impact Preview as:
- plan-driven
- dependency-driven
- fix-history informed

Later, you can enrich with cloud APIs / runtime signals.

---

### 20) Make sure every section has ONE “next action”
At the end of each major section:
- a button
- or a command snippet
- or a link

No dead ends.

---

## Suggested Final Navigation (Clean)
- Features
- Impact Preview (Blast Radius)
- Use Cases
- Demo
- Docs
- GitHub
- Get Started

---

## Quick Wins You Can Ship in < 1 Day

1. Add above-the-fold install + demo snippet (pipx)
2. Simplify CTAs to one primary + one secondary
3. Add trust/privacy callout near hero
4. Add a CI snippet section (even “coming soon”)
5. Add “Preview” badge on Blast Radius if not shipped

---

## Copy Blocks You Can Paste

### Trust / Safety block
> Local-first by default. Stores fixes in `~/.fixdoc`.  
> Git sync is optional. Private fixes never sync.  
> Redaction support helps mask common secrets before saving.

### Hero subhead (recommended)
> Capture, search, and share Terraform & Kubernetes fixes—then warn in CI when a change matches something your team already fixed.

### Demo block (recommended)
```bash
pipx install fixdoc
fixdoc demo tour
terraform show -json plan.tfplan > plan.json
fixdoc analyze plan.json --impact
```

---

## If You Want an Even Stronger Version of the Blast Radius Section
Add a “Real vs Preview” split:

- **Shipped now:** Impact Preview from Terraform plan JSON + fix-history overlay
- **Coming soon:** deeper semantic impact mapping, org-wide policies, PR annotations

This preserves trust while still marketing the future.

---

End of file.
