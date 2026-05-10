# ClawHub Skills Research Report

**Date:** 2026-05-05
**Platform:** ClawHub (https://clawhub.ai/) — Public skill registry for OpenClaw
**GitHub:** https://github.com/openclaw/clawhub
**Stats:** 52.7k skills, 180k users, 12M downloads, 4.8 avg rating
**CLI installed:** v0.12.2 at `/home/dung/.npm-global/bin/clawhub`

---

## CLI Quick Reference

```bash
clawhub install <slug>          # Install a skill
clawhub uninstall <slug>        # Remove a skill (asks confirmation)
clawhub uninstall <slug> --yes  # Remove without prompt
clawhub list                    # List installed skills
clawhub update --all            # Update all installed skills
clawhub search <query>          # Vector search
clawhub explore --sort installs --limit 20  # Browse by popularity
clawhub inspect <slug>          # View skill details without installing
clawhub login                   # Auth via browser or --token clh_...
```

Config: `~/.config/clawhub/config.json`
Default install dir: `<workdir>/skills/<slug>/`
Lockfile: `<workdir>/.clawhub/lock.json`

---

## Part 1: Requested Skills Verification

### SECURITY SKILLS

| # | Requested Slug | Found? | Actual Slug | Installs | Downloads | Stars | Status |
|---|---------------|--------|-------------|----------|-----------|-------|--------|
| 1 | skill-vetter | YES | `skill-vetter` | 4,275 | 230,070 | 1,040 | SAFE - Benign, no code files, instruction-only vetting checklist |
| 2 | azhua-skill-vetter | YES | `azhua-skill-vetter` | 14 | 1,921 | 0 | SAFE - Same concept, different author, instruction-only |
| 3 | arc-trust-verifier | PAGE EXISTS, API 404 | N/A | N/A | N/A | N/A | Platform-owned stub (`@skills`), no real content — likely placeholder |

**RECOMMENDATION:** Install `skill-vetter` (dominant choice: 4.2k installs, 230k downloads, 1k stars). `azhua-skill-vetter` is a fork with minimal traction. `arc-trust-verifier` does not exist as a usable skill.

---

### HIGH PRIORITY SKILLS

#### Browser Automation

| # | Slug | Exists? | Installs | Downloads | Stars | Owner | Description |
|---|------|---------|----------|-----------|-------|-------|-------------|
| 1 | `agent-browser-clawdbot` | YES | 768 | 102,853 | 368 | matrixy | Headless browser CLI for AI agents, accessibility tree + ref-based selection |
| 2 | `browser-use` | YES | 448 | 39,486 | 94 | shawnpana | Browser automation for testing, forms, screenshots, data extraction |
| 3 | `browser` | YES | 268 | 13,525 | 2 | pshotts | Headless browser to navigate, interact, extract text from URLs |
| 4 | `agent-browser` | PAGE EXISTS, API 404 | N/A | N/A | N/A | @skills | Platform stub, no real content |

**RECOMMENDATION:** `agent-browser-clawdbot` is the clear winner (768 installs, 102k downloads, 368 stars). Purpose-built for AI agent workflows.

#### n8n Automation

| # | Slug | Exists? | Installs | Downloads | Stars | Owner | Description |
|---|------|---------|----------|-----------|-------|-------|-------------|
| 1 | `n8n-workflow-automation` | YES | 301 | 29,150 | 138 | KOwl64 | Designs n8n workflow JSON with error handling, retries, HITL review queues |
| 2 | `n8n` | YES | 193 | 17,679 | 54 | thomasansems | Manage n8n workflows/automations via API - list, activate, check executions |

**RECOMMENDATION:** Both are useful. `n8n-workflow-automation` has more stars (138 vs 54) and focuses on DESIGNING workflows. `n8n` focuses on MANAGING existing instances via API. For MMO automation, get both — or start with `n8n-workflow-automation`.

#### Image/Video/Design

| # | Slug | Exists? | Installs | Downloads | Stars | Owner | Description |
|---|------|---------|----------|-----------|-------|-------|-------------|
| 1 | `image-generation` | YES | 86 | 7,305 | 9 | ivangdavila | AI images: GPT Image, Gemini, FLUX, Imagen — prompt engineering + editing |
| 2 | `best-image-generation` | YES | 84 | 10,421 | 8 | evolinkai | Best quality AI image gen (~$0.12-0.20/image) via EvoLink API |
| 3 | `best-image` | YES | 2 | 807 | 2 | pharmacist9527 | Same EvoLink API concept, lower traction |
| 4 | `ai-video-gen` | YES | 35 | 6,110 | 6 | rhanbourinajd | End-to-end video: text-to-image-to-video, voiceover, FFmpeg assembly |
| 5 | `canva-connect` | YES | 11 | 3,524 | 3 | coolmanns | Manage Canva designs/assets/folders via Connect API |

**RECOMMENDATION:** `image-generation` (broadest provider support) for general use. `ai-video-gen` for video content creation (MMO content). `canva-connect` only if you actively use Canva.

#### Social Media / Content Distribution

| # | Slug | Exists? | Installs | Downloads | Stars | Owner | Description |
|---|------|---------|----------|-----------|-------|-------|-------------|
| 1 | `postiz` | YES | 51 | 9,310 | 32 | nevo-david | Schedule to 28+ channels (X, LinkedIn, Reddit, IG, FB, TikTok, YouTube, etc.) |
| 2 | `x-api` | YES | 59 | 6,729 | 44 | lobstergener... | Post to X/Twitter via official API with OAuth 1.0a |
| 3 | `bluesky` | YES | 20 | 6,042 | 16 | jeffaf | Full Bluesky CLI: post, reply, like, repost, follow, search, images |
| 4 | `bird-twitter` | YES | 27 | 3,082 | 9 | chuhuilove | X/Twitter CLI via bird tool — GraphQL-based, fast |

**NOTE:** No single "bird" skill. The slug `bird` is a platform stub. The actual X/Twitter skills are `x-api` (official API) and `bird-twitter` (CLI wrapper).

**RECOMMENDATION:** `postiz` for multi-platform scheduling (biggest reach). `x-api` for dedicated X/Twitter API work. `bluesky` for Bluesky presence.

#### Data / Pipeline

| # | Slug | Exists? | Installs | Downloads | Stars | Owner | Description |
|---|------|---------|----------|-----------|-------|-------|-------------|
| 1 | `csv-pipeline` | YES | 41 | 5,483 | 2 | gitgoodordietrying | Process, transform, analyze CSV/JSON — filter, join, aggregate, dedupe |
| 2 | `duckdb-cli` | YES | 2 | 356 | 0 | proxx | DuckDB CLI specialist for SQL analysis, CSV/Parquet/JSON |
| 3 | `duckdb-en` | PAGE EXISTS, API 404 | N/A | N/A | N/A | @skills | Platform stub |

**RECOMMENDATION:** `csv-pipeline` for general data work. `duckdb-cli` exists but minimal traction (2 installs).

#### DevOps / Docker

| # | Slug | Exists? | Installs | Downloads | Stars | Owner | Description |
|---|------|---------|----------|-----------|-------|-------|-------------|
| 1 | `docker` | YES | 157 | 11,683 | 21 | ivangdavila | Containers, images, Compose, networking, volumes, production hardening |
| 2 | `agentic-devops` | PAGE EXISTS, API 404 | N/A | N/A | N/A | @skills | Platform stub |
| 3 | `docker-deploy` | PAGE EXISTS, API 404 | N/A | N/A | N/A | @skills | Platform stub |

**RECOMMENDATION:** `docker` is the only real usable skill here. `agentic-devops` and `docker-deploy` are platform stubs.

---

### MEDIUM PRIORITY SKILLS

| # | Slug | Exists? | Installs | Downloads | Stars | Description |
|---|------|---------|----------|-----------|-------|-------------|
| 1 | `agent-memory` | YES | 422 | 24,328 | 26 | Persistent memory: store facts, learn, recall, track entities |
| 2 | `agent-memory-ultimate` | PAGE ONLY | N/A | N/A | N/A | Platform stub |
| 3 | `affiliate-master` | YES | 10 | 3,318 | 1 | Full-stack affiliate automation, FTC-compliant, multi-network |
| 4 | `affiliate` | YES | 0 | 282 | 0 | Affiliate marketing system builder — finds high-commission programs |
| 5 | `biz-reporter` | YES | 10 | 1,764 | 0 | BI reports from GA4, Search Console, Stripe, social metrics |
| 6 | `cron` | YES | 86 | 6,224 | 6 | Local-first recurring schedule engine for reminders/tasks |
| 7 | `cron-scheduling` | YES | 73 | 8,712 | 7 | Cron + systemd timers, timezone-aware, failure monitoring |
| 8 | `seo` | YES | 111 | 12,199 | 25 | SEO specialist: audits, content writing, keywords, link building |
| 9 | `seo-audit` | PAGE ONLY | N/A | N/A | N/A | Platform stub |
| 10 | `seo-analyzer` | PAGE ONLY | N/A | N/A | N/A | Platform stub |

**RECOMMENDATIONS:**
- Memory: `agent-memory` (not `agent-memory-ultimate` which is a stub)
- Affiliate: `affiliate-master` has more substance
- Scheduling: `cron-scheduling` (more downloads) or `cron` (more installs) — similar functionality
- SEO: `seo` (dominant: 111 installs, 25 stars, comprehensive)

---

## Part 2: Platform Stubs vs Real Skills

Several slugs return HTTP 200 but contain only "Agent skill by @skills on ClawHub" — these are **platform stubs** with no real content. They cannot be installed via API.

**Stubs (avoid):** `agent-browser`, `bird`, `duckdb-en`, `agent-memory-ultimate`, `seo-audit`, `seo-analyzer`, `docker-deploy`, `agentic-devops`, `arc-trust-verifier`

**Always verify with:** `clawhub inspect <slug>` before installing.

---

## Part 3: Top 10 MMO + Vibe Coding Skills (Ranked)

Ranked by composite score: installs × downloads × stars × MMO relevance.

| Rank | Slug | Name | Installs | Downloads | Stars | MMO Use Case |
|------|------|------|----------|-----------|-------|-------------|
| 1 | `self-improving-agent` | Self-Improving Agent | 6,483 | 421,632 | 3,467 | Core agent skill — captures learnings across all MMO tasks |
| 2 | `agent-browser-clawdbot` | Agent Browser | 768 | 102,853 | 368 | Browser automation for scraping, posting, monitoring |
| 3 | `browser-use` | Browser Use | 448 | 39,486 | 94 | Alt browser automation — testing, forms, data extraction |
| 4 | `agent-memory` | Agent Memory | 422 | 24,328 | 26 | Persistent context across sessions — remembers strategies |
| 5 | `n8n-workflow-automation` | n8n Workflow Automation | 301 | 29,150 | 138 | Design automation workflows with error handling |
| 6 | `copywriting` | Copywriting | 252 | 18,626 | 35 | Persuasive copy for landing pages, emails, ads |
| 7 | `n8n` | n8n | 193 | 17,679 | 54 | Manage n8n workflows via API |
| 8 | `docker` | Docker | 157 | 11,683 | 21 | Deploy MMO apps, SaaS products |
| 9 | `productivity` | Productivity | 237 | 20,345 | 61 | Time blocking, goal tracking, energy management |
| 10 | `seo` | SEO | 111 | 12,199 | 25 | Site audits, keyword research, content optimization |

---

## Part 4: Additional MMO-Relevant Skills Worth Noting

| Category | Slug | Installs | Description |
|----------|------|----------|-------------|
| Content | `postiz` | 51 | Schedule to 28+ social platforms |
| Content | `youtube` | 84 | YouTube search, transcripts, channel info |
| Content | `tiktok` | 13 | TikTok growth OS, hooks, scripts, analytics |
| Content | `linkedin` | 106 | LinkedIn automation for networking/leads |
| Content | `email-marketing` | 41 | Email deliverability, sequences, campaigns |
| Content | `ai-video-gen` | 35 | End-to-end AI video generation pipeline |
| Content | `image-generation` | 86 | Multi-provider AI image generation |
| Marketing | `lead-generation` | 14 | Find buyers in Twitter/IG/Reddit conversations |
| Marketing | `social-media-marketing` | 14 | Solopreneur social media strategy builder |
| Marketing | `landing-page` | 5 | High-converting landing page builder |
| Marketing | `monetize` | 5 | Pricing/revenue strategies for indie products |
| Marketing | `saas` | 3 | Build/scale profitable SaaS |
| Marketing | `ads` | 1 | Paid acquisition strategy |
| Marketing | `funnel` | 0 | Marketing/sales funnel builder |
| Data | `csv-pipeline` | 41 | CSV/JSON processing pipeline |
| Data | `biz-reporter` | 10 | BI reports from GA4, Stripe, social |
| Data | `analytics` | 43 | Privacy-first analytics deployment |
| Scheduling | `cron` | 86 | Recurring task scheduling |
| Scheduling | `cron-scheduling` | 73 | Cron + systemd timers |
| Web | `web-scraping` | 46 | Extract structured data from websites |
| Web | `wordpress` | 23 | WordPress REST API CLI |
| Web | `ghost-cms` | 1 | Ghost CMS blog management |
| Vibe Coding | `vibe-coding` | 38 | AI-assisted dev techniques and workflows |

---

## Part 5: Security Assessment

**ClawHub security model:**
- Each skill page shows a security scan section (Purpose, Instruction Scope, Install Mechanism, Credentials, Persistence & Privilege)
- Skills with no code files (instruction-only) are lowest risk
- Skills requesting env vars/API keys should be reviewed manually
- The `skill-vetter` skill provides a checklist for pre-install security review

**General safety observations:**
- `skill-vetter`: Benign, no code, instruction-only (SAFEST tier)
- `azhua-skill-vetter`: Same category, benign (SAFEST tier)
- Platform stubs (`@skills` owned): Likely safe but empty/unused
- Most community skills: Require API keys but follow standard patterns
- No paid skills on ClawHub — all MIT-0 licensed

---

## Part 6: Recommended Install Priority for MMO + Vibe Coding

### Tier 1 — Install First (Core Infrastructure)
1. `skill-vetter` — Security vetting before installing anything else
2. `self-improving-agent` — Core learning/correction capture
3. `agent-browser-clawdbot` — Browser automation backbone
4. `agent-memory` — Persistent context across sessions

### Tier 2 — Install for Content + Marketing
5. `copywriting` — Persuasive copy for all MMO content
6. `seo` — SEO optimization for organic traffic
7. `postiz` — Multi-platform social scheduling (28+ channels)
8. `image-generation` — AI image creation for content

### Tier 3 — Install for Automation + Data
9. `n8n-workflow-automation` — Workflow design with error handling
10. `docker` — Deployment infrastructure
11. `csv-pipeline` — Data processing
12. `cron-scheduling` — Recurring task management

### Tier 4 — Install as Needed
13. `biz-reporter` — BI dashboards
14. `affiliate-master` — Affiliate marketing automation
15. `email-marketing` — Email campaigns
16. `lead-generation` — Lead finding
17. `linkedin` — Professional networking automation
18. `vibe-coding` — AI-assisted dev workflows

---

## Unresolved Questions

1. **Platform stubs:** Skills like `agent-browser`, `bird`, `duckdb-en`, etc. show as pages but return "Skill not found" via API. Are these deprecated, upcoming, or platform-internal? Unclear from docs.
2. **Security scan API:** The `/api/skill` endpoint returns `securityScan: N/A` for all skills, but the web UI shows detailed scan results. The scan data may be embedded in the client-rendered page, not available via the JSON API.
3. **`clawhub explore --sort installsAllTime`** appears to ignore the sort flag and returns newest instead. May be a CLI bug in v0.12.2.
4. **Rating system:** ClawHub homepage shows "4.8 avg rating" but individual skill API responses don't include a rating field. Rating may be computed differently or displayed only on web.
5. **Skill compatibility:** No data on which skills work with which agent platforms (Claude, OpenClaw, etc.). All skills appear to be SKILL.md-based text skills but some include Python scripts requiring specific dependencies.
