# Research: Gemini CLI Native PDF Processing

**Date:** 2026-05-08
**Topic:** How Gemini CLI (github.com/google-gemini/gemini-cli) handles PDF files natively
**Status:** COMPLETE

---

## Q1: How Does Gemini CLI Read PDFs? Token Cost Per Page?

### Mechanism

Gemini CLI uses the Gemini API's native PDF support. There are two processing paths:

1. **Built-in `read_file` tool** -- Supports PDF natively alongside text, images, audio. The model calls `read_file(file_path="doc.pdf")` and the API handles decoding.
2. **`@{file.pdf}` injection in custom commands** -- TOML commands with `@{path}` auto-encode PDFs as multimodal input.
3. **Stdin piping** -- `cat doc.pdf | gemini -p "analyze this"` auto-detects binary format.

Under the hood, the Gemini API processes PDFs by rendering each page as an image (scaled to 768x768 minimum, 3072x3072 maximum, preserving aspect ratio). Each page becomes a vision input.

### Token Cost

| Metric | Value | Source |
|--------|-------|--------|
| **Tokens per PDF page** | **258 tokens** (same as a 384x384 image) | Gemini API docs/tokens |
| **Max PDF size** | 50 MB | Gemini API document-processing |
| **Max pages per request** | 1,000 pages | Gemini API document-processing |
| **Max pages across multiple PDFs** | 1,000 pages total in single request | Gemini API document-processing |

### Gemini 3 Enhancement

Gemini 3 models extract **native text** from PDFs separately:
- Native embedded text is extracted and provided to the model at no token cost
- Page images are still counted as IMAGE modality tokens (258/page)
- This means text-heavy PDFs effectively cost ~258 tokens/page (image only) since text is free

### Cost Example

A 100-page PDF costs approximately **25,800 tokens** (100 x 258). With a 1M token context window, that leaves ~974K tokens for conversation, tools, and output.

---

## Q2: Single-Session Processing? Context Fills Up?

### Context Window

| Model | Context Window |
|-------|---------------|
| Gemini 2.5 Pro | 1M tokens |
| Gemini 2.5 Flash | 1M tokens |

### Theoretical PDF Capacity

- 1M tokens / 258 tokens per page = **~3,875 pages** theoretical max
- BUT: context includes system prompt, conversation history, tool calls/responses, and model output
- Practical limit: **~3,000-3,500 pages** for PDF-only, much less with active conversation
- Hard API limit: **1,000 pages** regardless of context capacity

### What Happens When Context Fills Up

Gemini CLI has **context compression** (see Q3). When triggered:
1. Earlier conversation turns are summarized
2. The compressed summary replaces detailed history
3. PDF content from earlier turns may be reduced to summaries
4. Session data is preserved for rewind/reconstruction

### Multi-PDF Strategy

For PDFs exceeding practical limits, use **multiple headless invocations** rather than one giant session:

```bash
# Process pages 1-100, 101-200, etc. via split PDFs
for part in doc_part_*.pdf; do
  gemini -p "Extract all text from this PDF verbatim: @$part" --output-format text >> output.md
done
```

---

## Q3: How Does compressionThreshold Work? Does Compression Lose Earlier PDF Pages?

### Setting Location

In `settings.json`: `model.compressionThreshold`

```
"The fraction of context usage at which to trigger context compression"
Default: 0.5
```

### Behavior

1. Gemini CLI monitors token usage relative to the model's context window
2. When usage hits 50% (default), compression triggers
3. The model generates a summary of earlier conversation turns
4. The summary replaces the detailed turns, freeing context space
5. Process repeats each time the threshold is hit again

### Does Compression Lose Earlier PDF Pages?

**YES -- partially.** Here is the nuance:

- The **raw PDF page images** from earlier turns are dropped during compression
- A **summary** of what was discussed about those pages is retained
- The model can no longer "re-read" specific pages from compressed turns
- However, session data (stored at `~/.gemini/tmp/<project_hash>/chats/`) preserves the full history for **rewind** purposes

### Verification from Official Docs

The rewind documentation states: "Rewind works across chat compression points by reconstructing the history from stored session data." This confirms the full history is saved to disk even after compression, but the in-context representation is reduced.

### Mitigation Strategies

| Strategy | How | Trade-off |
|----------|-----|-----------|
| **Write to disk early** | Use `write_file` to save extracted content before compression | Extra tool calls, but data is safe |
| **Increase threshold** | Set `compressionThreshold: 0.8` | More context for PDFs, but less room for conversation |
| **Smaller PDF chunks** | Process 50-page sections per invocation | More orchestration, but no compression risk |
| **Use headless mode** | One-shot per section, no conversation history | No compression at all, output goes to stdout |

### Recommended Setting for PDF Processing

```json
{
  "model": {
    "compressionThreshold": 0.8
  }
}
```

This gives PDFs 800K of the 1M context before compression triggers (vs 500K default).

---

## Q4: Can the Model Write to Files During Processing?

**YES.** Gemini CLI has full file write capabilities.

### Built-in File Tools

| Tool | Purpose | Requires Approval |
|------|---------|-------------------|
| `write_file` | Create/overwrite files | Yes (sandbox confirmation) |
| `replace` | Precise text edits in existing files | Yes (sandbox confirmation) |
| `read_file` | Read any file (PDF, image, text, audio) | No |
| `read_many_files` | Read multiple files at once | No |
| `list_directory` | List directory contents | No |
| `glob` | Find files by pattern | No |
| `grep_search` | Search file contents | No |

### Workflow: Read PDF, Write Extracted Content to Disk

```
User: Read this PDF and save extracted text to output.md
Model: [calls read_file("doc.pdf")] -> [processes content] -> [calls write_file("output.md", content)]
```

The model can read a PDF, process it, and write results to disk **in the same turn**. This is critical for avoiding context compression loss -- extract and save immediately.

### Checkpointing

Optional auto-checkpointing creates git snapshots before file modifications:

```json
{
  "general": {
    "checkpointing": {
      "enabled": true
    }
  }
}
```

Snapshots stored at `~/.gemini/history/<project_hash>`. Use `/restore` to revert.

---

## Q5: Headless Mode (`-p`): One-Shot PDF Processing? Maximum Limits?

### How Headless Mode Works

The `-p` flag triggers non-interactive mode:
- Processes one prompt, outputs result, exits
- Can also be triggered by non-TTY environment
- Stdin content is appended before the prompt

### Syntax

```bash
# Basic headless
gemini -p "Analyze this PDF for key findings"

# With stdin piping
cat report.pdf | gemini -p "Extract all tables from this PDF"

# With file reference in prompt
gemini -p "Read @report.pdf and summarize each section"

# With output format
gemini -p "Extract data from @report.pdf" --output-format json
```

### Output Formats

| Format | Flag | Description |
|--------|------|-------------|
| `text` | `--output-format text` | Model text output only (default) |
| `json` | `--output-format json` | Single JSON object with full response |
| `stream-json` | `--output-format stream-json` | JSONL events (init, message, tool_use, tool_result, error, result) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |
| 42 | Input error |
| 53 | Turn limit exceeded |

### Turn Limit

Setting: `model.maxSessionTurns` (default: `-1` = unlimited)

In headless mode, the model still performs multiple tool-call turns if needed (e.g., read PDF -> process -> write file). The default is unlimited turns. Set a limit to prevent runaway costs:

```json
{
  "model": {
    "maxSessionTurns": 20
  }
}
```

### Practical Limits for Headless PDF Processing

- **Single PDF**: Up to 1,000 pages / 50 MB (API hard limit)
- **No session memory**: Each `-p` invocation is independent (unless using `--resume`)
- **Token cost**: Same as interactive -- 258 tokens/page
- **Quota**: Free tier = 1,000 requests/day (Google account) or 250/day (API key unpaid)

---

## Q6: Does `--output-format text` Capture Just Model's Text Output?

**YES.** The `text` format outputs only the model's final text response to stdout.

### Format Comparison

| Format | What You Get | Use Case |
|--------|-------------|----------|
| `text` | Just the model's text response | Piping to files, scripts |
| `json` | Single JSON: `{response, history, stats}` | Programmatic access to full data |
| `stream-json` | JSONL events in real-time | CI/CD integration, progress monitoring |

### Practical Examples

```bash
# Extract text, save to file
gemini -p "Read @report.pdf and extract all text verbatim" --output-format text > report.md

# Extract structured data, parse with jq
gemini -p "Extract all tables from @report.pdf as JSON" --output-format json | jq -r '.response' > tables.json

# Stream events for monitoring
gemini -p "Analyze @report.pdf" --output-format stream-json | grep '"type":"result"'
```

**Important**: `text` format does NOT include tool calls, tool results, or intermediate steps. Only the model's final text output reaches stdout.

---

## Q7: Stdin Piping: How Does "Auto-Detects PNG/JPG/PDF/WAV/MP3" Work?

### Mechanism

When content arrives via stdin, Gemini CLI inspects the **magic bytes** (file signature) to determine the content type, regardless of file extension or piped command.

### Binary Detection

The CLI reads the first few bytes of stdin input and matches against known file signatures:

| Bytes | Detected Type |
|-------|---------------|
| `%PDF` | PDF |
| `\x89PNG` | PNG |
| `\xFF\xD8\xFF` | JPEG/JPG |
| `RIFF....WAVE` | WAV |
| `\xFF\xFB` or `\x49\x44\x33` | MP3 |

### Supported Use Patterns

```bash
# Direct file piping
cat report.pdf | gemini -p "Summarize this"
cat screenshot.png | gemini -p "Describe this image"
cat audio.mp3 | gemini -p "Transcribe this"

# Process substitution
gemini -p "Analyze this" < report.pdf

# Combined with prompt text
cat data.pdf | gemini -p "Extract all numerical data from this PDF and format as CSV"
```

### Stdin + Prompt Combination

The docs state: "Prompt text. Appended to stdin input if provided." This means:
1. Stdin content is loaded first (becomes the multimodal input)
2. The `-p` prompt text is appended as the instruction
3. Both are sent to the model in a single request

### Limitation

Stdin piping works for **one file at a time**. For multiple files, use `@` file references in the prompt or `read_many_files` tool.

---

## Q8: Session Management: Can You Resume with `--resume` and Continue?

**YES.** Full session management with resume capability.

### Resume Methods

| Method | Command | Behavior |
|--------|---------|----------|
| Latest session | `gemini --resume` or `gemini -r` | Resumes most recent session |
| By index | `gemini --resume 1` | Resumes session #1 from session list |
| By UUID | `gemini --resume <uuid>` | Resumes specific session |

### Session Storage

- Location: `~/.gemini/tmp/<project_hash>/chats/`
- Auto-saved after each turn
- Retention: 30 days default, configurable via `general.sessionRetention`

### Interactive Session Management

| Command | Purpose |
|---------|---------|
| `/resume` | Open session browser with search/preview |
| `/resume save <name>` | Save named checkpoint |
| `/resume list` | List saved checkpoints |
| `/resume resume <name>` | Resume named checkpoint |

### Relevance to PDF Processing

You can start a PDF processing session interactively, then resume it later:

```bash
# Start session
gemini
> Read @large-report.pdf and extract section 1

# Later, resume and continue
gemini --resume
> Now extract section 2 from the same PDF
```

**Important**: Resumed sessions include full conversation history (not compressed). The PDF content from earlier turns is still in context. This means the context window fills up across resumed sessions too -- compression still applies.

### Session + Headless Mode

```bash
# Process PDF in headless mode, creating a session
gemini -p "Read @report.pdf and extract key data" 

# Resume that session later to ask follow-up questions
gemini --resume
> What were the total revenue figures on page 5?
```

---

## Q9: Custom Skills/Extensions: Can You Define Custom Slash Commands That Process Files?

**YES.** Three extensibility mechanisms support this.

### A. Custom Commands (Simplest)

TOML files in `~/.gemini/commands/` (global) or `.gemini/commands/` (project):

```toml
# ~/.gemini/commands/pdf-extract.toml
description = "Extract text from a PDF file"
prompt = """
Read the PDF at: {{args}}

Extract all text content verbatim. Use write_file to save to the same directory with .md extension.

ZERO-HALLUCINATION: Output verbatim text only. No summarization.
"""
```

Usage: `/pdf-extract /path/to/report.pdf`

### B. Custom Commands with Shell Execution

```toml
# ~/.gemini/commands/pdf-vision.toml
description = "Process PDF using vision-based page extraction"
prompt = """
Execute the PDF vision extraction workflow for: {{args}}

Step 1: Run the split script: !{python3 /path/to/split.py "{{args}}"}
Step 2: Read each page image using read_file
Step 3: Extract content verbatim from each page
Step 4: Run the merge script: !{python3 /path/to/merge.py --output "result.md"}
"""
```

### C. Commands with @{file} Injection

```toml
# ~/.gemini/commands/analyze-pdf.toml
description = "Analyze PDF with multimodal understanding"
prompt = """
Analyze the following PDF document thoroughly:
@{args}

Provide:
1. Document summary (2-3 paragraphs)
2. Key data tables (as markdown)
3. Action items or conclusions
"""
```

The `@{path}` syntax correctly encodes PDFs as multimodal input -- this is explicitly documented: "If the path points to a supported image, PDF, audio, or video file, it will be correctly encoded and injected as multimodal input."

### D. Agent Skills

Skills defined by `SKILL.md` files in `~/.gemini/skills/<name>/`:
- Discovery/activation/consent lifecycle
- Model auto-activates based on description matching user intent
- Can include scripts, references, and context files

### E. Full Extensions

Packages at `~/.gemini/extensions/<name>/` with manifest (`gemini-extension.json`):
- Bundle commands, skills, MCP servers, and context files
- Loaded at startup
- Shareable

---

## Trade-Off Matrix: PDF Processing Approaches

| Approach | Max Pages | Context Risk | Automation | Complexity | Best For |
|----------|-----------|-------------|------------|------------|----------|
| **Inline `read_file`** | ~3,000 | High (compression) | Manual | Low | Quick analysis |
| **`@{file}` in custom command** | ~3,000 | High (compression) | Semi-auto | Low | Reusable extraction |
| **Stdin pipe + headless** | 1,000 per run | None (one-shot) | Full auto | Low | Batch processing |
| **Custom command + scripts** | Unlimited (chunked) | Low (write early) | Semi-auto | Medium | Complex layouts |
| **Extension package** | Unlimited (chunked) | Low (write early) | Full auto | High | Production pipelines |

---

## Concrete Examples

### Example 1: Quick PDF Summary (Interactive)

```bash
gemini
> Summarize @quarterly-report.pdf in 5 bullet points
```

### Example 2: Extract All Text to Markdown (Headless)

```bash
gemini -p "Read @report.pdf. Extract ALL text verbatim. No summarization. Output plain text only." \
  --output-format text > report-extracted.md
```

### Example 3: Batch Process Multiple PDFs (Shell Script)

```bash
#!/bin/bash
for pdf in ./pdfs/*.pdf; do
  filename=$(basename "$pdf" .pdf)
  gemini -p "Read @$pdf and extract all text verbatim." \
    --output-format text > "./output/${filename}.md"
done
```

### Example 4: Custom Command for PDF Processing

```toml
# ~/.gemini/commands/pdf-to-md.toml
description = "Convert PDF to Markdown with verbatim text extraction"
prompt = """
Read the PDF file at: {{args}}

Instructions:
1. Use read_file to load the PDF
2. Extract ALL text content verbatim -- no summarization, no hallucination
3. Preserve document structure (headings, paragraphs, lists)
4. Use write_file to save output as .md in the same directory as the input

Output format: Clean Markdown with proper heading hierarchy.
"""
```

### Example 5: PDF Analysis with JSON Output (CI/CD)

```bash
gemini -p "Analyze @financial-report.pdf. Extract: revenue, costs, profit, year-over-year change. Output as JSON." \
  --output-format json | jq -r '.response' > financial-data.json
```

### Example 6: Process Large PDF in Chunks (Avoiding Compression)

```bash
# Split PDF first with pdftk or python
pdftk large-report.pdf cat 1-50 output part1.pdf
pdftk large-report.pdf cat 51-100 output part2.pdf

# Process each chunk in separate headless invocations
gemini -p "Read @part1.pdf and extract all text verbatim" --output-format text > full-output.md
gemini -p "Read @part2.pdf and extract all text verbatim" --output-format text >> full-output.md
```

---

## Ranked Recommendation

### For PDF Text Extraction

**#1 Headless mode with `--output-format text`** -- simplest, no compression risk, scriptable, output goes directly to disk. Use for batch processing.

**#2 Custom command with `@{file}` injection** -- reusable, can include extraction rules, works interactively. Good for ad-hoc analysis.

**#3 Custom command + Python scripts** -- for complex PDFs with tables, images, multi-column layouts. More setup but handles edge cases.

### Settings Recommendation

```json
{
  "model": {
    "compressionThreshold": 0.8,
    "maxSessionTurns": 20
  }
}
```

- Higher compression threshold (0.8) preserves more PDF content before summarization
- Turn limit (20) prevents runaway tool-call loops
- Both configurable per-project in `.gemini/settings.json`

---

## Source Credibility Assessment

| Source | Credibility | Key Data Points |
|--------|------------|-----------------|
| Gemini API docs/document-processing | HIGH (official Google) | 258 tokens/page, 50MB/1000 pages limit |
| Gemini API docs/tokens | HIGH (official Google) | Image token methodology, Gemini 3 native text |
| Gemini CLI GitHub README | HIGH (official Google, Apache 2.0) | 1M context, built-in file ops, headless mode |
| docs/cli/headless.md | HIGH (official) | Output formats, exit codes |
| docs/cli/custom-commands.md | HIGH (official) | TOML spec, @{file} multimodal injection |
| docs/cli/session-management.md | HIGH (official) | Resume, session storage, retention |
| docs/cli/settings.md | HIGH (official) | compressionThreshold, maxSessionTurns |
| docs/cli/rewind.md | HIGH (official) | Compression + session data preservation |
| docs/tools/file-system.md | HIGH (official) | read_file PDF support, write_file |
| docs/cli/tutorials/automation.md | HIGH (official) | Pipe examples, batch processing patterns |

---

## Limitations of This Research

1. **Token counting is API-level** -- Gemini CLI may add overhead (system prompt, tool definitions) not accounted for in the 258/page calculation. Practical capacity is lower than theoretical.
2. **No empirical testing done** -- All numbers from official docs, not measured. Actual behavior may differ for specific PDF types (scanned vs native text, encrypted, etc.).
3. **Gemini 3 native text extraction** -- The free native text feature was confirmed in API docs but behavior within Gemini CLI specifically (whether CLI benefits from it) was not empirically verified.
4. **Headless mode approval flow** unclear -- Shell commands in headless mode may still require sandbox approval depending on settings. The `--yolo` flag or trusted folders may bypass this, but this was not tested.
5. **Compression quality not measured** -- The quality of context compression summaries when applied to PDF content was not evaluated. "Rewind works across compression points" is documented but the reconstruction fidelity is unknown.

---

## Unresolved Questions

1. Does Gemini CLI's `read_file` benefit from Gemini 3's free native text extraction, or does it always use the image-based path?
2. What is the actual overhead of system prompt + tool definitions in Gemini CLI's context window? This affects the practical page limit.
3. Can `@{file.pdf}` in custom commands handle PDFs larger than the context window, or does it fail outright?
4. Does headless mode with shell commands (`!{...}`) bypass sandbox approval, or does it block waiting for confirmation?
5. What happens when compressionThreshold triggers during a multi-tool-call turn (e.g., model is mid-way through processing pages)?
