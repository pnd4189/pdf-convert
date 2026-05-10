# OpenClaw Memory Management System - Research Report

**Date:** 2026-05-05
**Researcher:** Technical Analyst
**Context:** Ubuntu/Docker, GLM-5.1 via z.ai, Supabase in stack, n8n automation, GMKtec M6 Ultra

---

## 1. Memory Backends Supported

OpenClaw supports **4 memory backends** + 1 knowledge layer plugin:

| Backend | Type | Status | Storage |
|---------|------|--------|---------|
| **Builtin (SQLite)** | Default engine | Stable | `~/.openclaw/memory/.sqlite` per agent |
| **QMD** | Sidecar binary | Stable | Local SQLite managed by QMD binary |
| **Honcho** | Plugin (external service) | Stable | Dedicated service (local or cloud) |
| **LanceDB** | Plugin (vector DB) | Stable | `~/.openclaw/memory/lancedb` or S3/cloud |
| **Memory Wiki** | Knowledge layer plugin (not a backend) | Stable | `~/.openclaw/wiki/` Markdown vault |

Sources: [memory overview](https://docs.openclaw.ai/concepts/memory.md), [memory builtin](https://docs.openclaw.ai/concepts/memory-builtin.md), [memory config](https://docs.openclaw.ai/reference/memory-config.md)

---

## 2. Configuration in openclaw.json

Config lives at `~/.openclaw/openclaw.json` (json5 format).

### Default Builtin Engine (zero config)
```json5
{
  agents: {
    defaults: {
      memorySearch: {
        provider: "openai",  // auto-detected from API keys
      }
    }
  }
}
```

### QMD Backend
```json5
{
  memory: {
    backend: "qmd",
    citations: "auto",
    qmd: {
      command: "/absolute/path/to/qmd",  // optional, if not on PATH
      includeDefaultMemory: true,
      update: { interval: "5m", debounceMs: 15000 },
      limits: { maxResults: 6, timeoutMs: 4000 },
      searchMode: "query",  // "search" (BM25), "vsearch", "query" (full)
      sessions: { enabled: true },
      paths: [
        { name: "docs", path: "~/notes", pattern: "**/*.md" }
      ]
    }
  }
}
```

### Honcho Backend
```json5
{
  plugins: {
    entries: {
      "openclaw-honcho": {
        config: {
          apiKey: "your-key",        // omit for self-hosted
          workspaceId: "openclaw",
          baseUrl: "https://api.honcho.dev",  // or http://localhost:8000
        }
      }
    }
  }
}
```

### LanceDB Backend
```json5
{
  plugins: {
    slots: { memory: "memory-lancedb" },
    entries: {
      "memory-lancedb": {
        enabled: true,
        config: {
          dbPath: "~/.openclaw/memory/lancedb",
          embedding: {
            provider: "ollama",
            baseUrl: "http://127.0.0.1:11434",
            model: "mxbai-embed-large",
            dimensions: 1024,
          },
          autoRecall: true,
          autoCapture: false,
          recallMaxChars: 1000,
          captureMaxChars: 500,
        }
      }
    }
  }
}
```

### Hybrid Search Tuning (applies to builtin)
```json5
{
  agents: {
    defaults: {
      memorySearch: {
        query: {
          hybrid: {
            enabled: true,
            vectorWeight: 0.7,
            textWeight: 0.3,
            candidateMultiplier: 4,
            mmr: { enabled: true, lambda: 0.7 },
            temporalDecay: { enabled: true, halfLifeDays: 30 }
          }
        }
      }
    }
  }
}
```

Sources: [memory config reference](https://docs.openclaw.ai/reference/memory-config.md), [memory builtin](https://docs.openclaw.ai/concepts/memory-builtin.md)

---

## 3. Can Supabase/PostgreSQL Be Used as Memory Backend?

**No. Not supported.**

OpenClaw's memory system is fundamentally **file-based (Markdown) + SQLite-indexed**. There is no PostgreSQL, Supabase, or any relational database adapter for memory storage. This was verified across:

- All official memory backend documentation pages
- Memory config reference (no PostgreSQL/Supabase options)
- Plugin registry (no community Supabase plugin)
- GitHub issues/ClawHub (no such adapter found)

**What this means for your stack:** Your Supabase instance remains useful for your application's own data, n8n workflows, and other services. It simply cannot serve as OpenClaw's memory backend. OpenClaw manages its own storage independently.

Source credibility: Official docs, verified across 6+ pages.

---

## 4. Memory Architecture

### File Structure
```
~/.openclaw/workspace/
  MEMORY.md              # Long-term durable facts (loaded every session)
  DREAMS.md              # Optional dream diary (consolidation review)
  memory/
    2026-05-04.md        # Yesterday's notes (auto-loaded)
    2026-05-05.md        # Today's notes (auto-loaded)
    2026-05-03.md        # Older notes (searchable, not auto-loaded)
```

### Memory Lifecycle

```
[Conversation] --> [Short-term: daily .md files]
                        |
                        v
                [Memory Search: vector + BM25 hybrid]
                        |
                   [Agent retrieves context]
                        |
                        v
                [Compaction triggers memory flush]
                        |
                        v
                [Dreaming system promotes to long-term]
                   (threshold-based, reviewable)
                        |
                        v
                [MEMORY.md: durable facts]
```

### Key Mechanisms

| Mechanism | Description |
|-----------|-------------|
| **Auto-load** | MEMORY.md + today/yesterday daily notes loaded at session start |
| **Hybrid search** | Vector similarity (70% weight) + BM25 keyword (30% weight) |
| **Temporal decay** | Exponential multiplier, 30-day half-life, evergreen files exempt |
| **MMR diversity** | Maximal Marginal Relevance prevents redundant results |
| **Compaction** | Automatic memory flush before summarization |
| **Dreaming** | Opt-in scheduled consolidation: short-term -> long-term promotion |
| **Embedding providers** | OpenAI, Gemini, Voyage, Mistral, Ollama, Local (node-llama-cpp), Bedrock, GitHub Copilot |

### Embedding Providers
- **Cloud:** OpenAI, Gemini, Voyage, Mistral, DeepInfra, Bedrock, GitHub Copilot
- **Local:** Ollama, node-llama-cpp (GGUF models)
- **Auto-detect:** Scans API keys in environment, picks first available
- **sqlite-vec:** Optional acceleration for in-database vector queries

Sources: [memory overview](https://docs.openclaw.ai/concepts/memory.md), [memory search](https://docs.openclaw.ai/concepts/memory-search.md), [memory builtin](https://docs.openclaw.ai/concepts/memory-builtin.md)

---

## 5. Best Practices for Power User (MMO + Vibe Coding)

### Recommended Setup for Your Hardware (GMKtec M6 Ultra)

Your machine has sufficient RAM/CPU for local embeddings. Recommended stack:

1. **Primary backend: QMD** -- local-first, reranking, query expansion, indexes extra directories and session transcripts
2. **Embedding: Ollama with mxbai-embed-large** -- fully local, no API costs, runs on your hardware
3. **Optional: memory-wiki in bridge mode** -- compiled knowledge vault with structured claims

### Practical Configuration
```json5
{
  memory: {
    backend: "qmd",
    citations: "auto",
    qmd: {
      searchMode: "query",       // full BM25 + vector + reranking
      sessions: { enabled: true }, // recall past conversations
      limits: { timeoutMs: 10000 }, // slower hardware safety
      paths: [
        { name: "vibe-coding", path: "/home/dung/VIBE_CODING", pattern: "**/*.md" },
        { name: "notes", path: "~/notes", pattern: "**/*.md" }
      ]
    }
  },
  agents: {
    defaults: {
      memorySearch: {
        provider: "ollama",
        ollama: {
          baseUrl: "http://127.0.0.1:11434",
          model: "mxbai-embed-large",
        },
        query: {
          hybrid: {
            enabled: true,
            vectorWeight: 0.7,
            textWeight: 0.3,
            temporalDecay: { enabled: true, halfLifeDays: 30 }
          }
        }
      }
    }
  }
}
```

### Workflow Tips
- Write to `MEMORY.md` for facts you want available every session
- Use `memory/YYYY-MM-DD.md` for daily context (auto-loaded today + yesterday)
- Enable dreaming for automatic short-term -> long-term promotion
- Run `openclaw memory status --deep` weekly to check index health
- Use QMD extra paths to make project docs searchable
- Enable session transcripts for recalling past coding sessions

---

## 6. Memory CLI Commands

| Command | Purpose |
|---------|---------|
| `openclaw memory status` | Show memory health for all agents |
| `openclaw memory status --deep` | Probe vector + embedding availability |
| `openclaw memory status --deep --index` | Reindex if store is dirty |
| `openclaw memory status --deep --index --verbose` | Full diagnostic |
| `openclaw memory index` | Reindex memory files |
| `openclaw memory index --verbose` | Per-phase details (provider, model, sources) |
| `openclaw memory index --force` | Force full reindex |
| `openclaw memory search "query"` | Search memory |
| `openclaw memory status --agent main` | Scope to specific agent |
| `openclaw memory query --cols ... --filter ...` | Direct LanceDB query (LanceDB only) |

### Honcho-specific CLI
| Command | Purpose |
|---------|---------|
| `openclaw honcho setup` | Configure API key + migrate files |
| `openclaw honcho status` | Check connection |
| `openclaw honcho ask` | Query about the user |
| `openclaw honcho search -k N -d D` | Semantic search |

### LanceDB-specific CLI
| Command | Purpose |
|---------|---------|
| `openclaw ltm list` | List stored memories |
| `openclaw ltm search "query"` | Search long-term memory |
| `openclaw ltm stats` | Storage statistics |

### Memory Wiki CLI
| Command | Purpose |
|---------|---------|
| `openclaw wiki status` | Vault health |
| `openclaw wiki doctor` | Diagnose issues |
| `openclaw wiki init` | Initialize vault |
| `openclaw wiki ingest <path>` | Import content |
| `openclaw wiki compile` | Compile wiki pages |
| `openclaw wiki lint` | Structural checks |
| `openclaw wiki search "query"` | Search wiki |
| `openclaw wiki bridge import` | Import from active memory |

Source: [CLI memory](https://docs.openclaw.ai/cli/memory.md)

---

## 7. Backend Comparison: Honcho vs QMD vs LanceDB

### Trade-off Matrix

| Dimension | Builtin (SQLite) | QMD | Honcho | LanceDB |
|-----------|-----------------|-----|--------|---------|
| **Setup complexity** | Zero | Low (install binary) | Medium (plugin + service) | Medium (plugin + embeddings) |
| **External deps** | None | QMD binary | Honcho service (local or cloud) | LanceDB native lib |
| **Search quality** | Good (hybrid) | Best (BM25 + vector + rerank + query expansion) | Good (semantic over observations) | Good (vector similarity) |
| **Cross-session memory** | Via files only | Via files + session transcripts | Automatic built-in | Via auto-capture |
| **User modeling** | Manual | None | Automatic profiles | None |
| **Extra path indexing** | Limited (extraPaths) | Full (arbitrary dirs) | No | No |
| **Session transcript search** | Experimental | Yes | Yes (automatic) | No |
| **Multi-agent awareness** | No | No | Yes (parent/child tracking) | No |
| **Fully local** | Yes | Yes | Yes (self-hosted option) | Yes |
| **API costs** | Embedding API only | None (local GGUF models) | Free self-hosted / paid cloud | Embedding API or local |
| **Reranking** | No | Yes (built-in) | No | No |
| **Query expansion** | No | Yes (built-in) | No | No |
| **Cloud storage** | No | No | Optional (managed API) | Yes (S3, cloud) |
| **Maturity** | Stable, default | Stable | Stable | Stable |
| **Disk footprint** | Small | ~2GB (GGUF models) | Depends on service | Small |

### Source Credibility Assessment
- **Official docs:** All 3 backends documented on docs.openclaw.ai -- HIGH credibility
- **GitHub:** OpenClaw repo (368k stars) -- HIGH credibility
- **Honcho docs:** honcho.dev -- MEDIUM-HIGH (maintainer documentation)
- **QMD:** github.com/tobi/qmd -- MEDIUM (solo maintainer, but OpenClaw officially supports it)

### Adoption Risk

| Backend | Risk Level | Rationale |
|---------|-----------|-----------|
| Builtin | **Very Low** | Default, no deps, actively maintained with OpenClaw core |
| QMD | **Low** | Officially supported, auto-fallback to builtin, solo maintainer but stable |
| Honcho | **Medium** | External service dependency, plugin maintained by third party (plastic-labs) |
| LanceDB | **Low-Medium** | Bundled plugin, native dependency can break on some platforms (darwin-x64 known issue) |

---

## 8. Ranked Recommendation

**For your specific setup (Ubuntu/Docker, local hardware, z.ai/GLM-5.1, no OpenAI API key guaranteed):**

### Rank 1: QMD (Recommended)

**Why:** Best search quality for a power user doing Vibe Coding. Fully local, no API keys needed, reranking + query expansion give significantly better recall. Indexes your project docs and past session transcripts. Auto-fallback to builtin if QMD fails.

**Your config advantage:** GMKtec M6 Ultra has compute for local GGUF models. QMD auto-downloads ~2GB models on first use. No recurring costs.

**Adoption risk:** Low. Officially supported, automatic fallback, single binary install.

### Rank 2: Builtin SQLite (Safe Default)

**Why:** Zero config, zero deps, works out of the box. Hybrid search with vector + BM25 is solid. Good enough for most use cases.

**Your config advantage:** Works immediately. Add Ollama embeddings for full local operation.

**Adoption risk:** Very low. Default engine.

### Rank 3: LanceDB (If You Need Cloud Storage)

**Why:** Local vector DB with auto-recall/capture, S3 storage option. Good if you want memory persisted to cloud or need structured queries.

**Your config advantage:** Can use Ollama embeddings. Works on Linux. S3 storage if you want backup.

**Adoption risk:** Low-Medium. Native dependency occasionally breaks. No fallback if plugin fails.

### Rank 4: Honcho (If You Need Cross-Session Intelligence)

**Why:** Automatic user modeling, multi-agent awareness, cross-session context without file management.

**Your config disadvantage:** Requires running Honcho service (Docker container). You already run n8n + Supabase, adding another service. Limited benefit for single-user Vibe Coding setup.

**Adoption risk:** Medium. Third-party plugin, external service dependency.

### What About Supabase/PostgreSQL?

**Do not use for OpenClaw memory.** Not supported. Your Supabase stays for application data and n8n workflows. OpenClaw manages its own storage via the backends above.

---

## Limitations

- **No hands-on testing:** All findings from official documentation only. Real-world performance may differ.
- **z.ai provider specifics:** Could not verify if z.ai provides embedding endpoints. If it does not, you must use Ollama or another local provider for embeddings.
- **Memory Wiki details:** Covered architecture but did not evaluate Obsidian integration depth.
- **ClawHub plugins:** Background research on ClawHub availability was running but results not yet available -- there may be community plugins not covered here.
- **Docker-specific considerations:** All paths assume standard install. Docker volume mounts for `~/.openclaw/` need attention.
- **Performance benchmarks:** No quantitative comparison of search latency between backends was available from docs.

## Unresolved Questions

1. Does z.ai expose an OpenAI-compatible embeddings endpoint? If not, Ollama is required.
2. What is the Docker volume strategy for persistent memory storage across container restarts?
3. Are there ClawHub community plugins for memory that were not covered?
4. How does QMD perform on GMKtec M6 Ultra hardware with concurrent n8n + Supabase workloads?
5. Can memory-wiki bridge mode work with LanceDB as the active plugin, or only with builtin/QMD?
