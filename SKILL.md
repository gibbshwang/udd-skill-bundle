---
name: udd
description: AX Universal Data Downloader — end-to-end automation for recurring downloads from corporate systems (login, navigation, filters, export). Use when the user wants a self-healing, scheduled Python project that downloads files from an intranet/ERP/admin site on a cron. Generates an independent project folder with Playwright + OS keyring auth + LLM-agnostic AI healing.
author: gibbs hwang
version: 0.1.0
---

# AX Universal Data Downloader

Generates a self-healing, scheduled Python project for automating corporate-system data downloads.
**Works identically under Claude Code, Gemini CLI, and Codex CLI.**

## ⚠️ Autonomous Mode Required

This skill runs a validation loop that executes scripts and edits files multiple times.
A permission prompt at each step will stall it. Start your CLI in autonomous mode:

| CLI | Launch command | Session toggle |
|-----|---------------|----------------|
| Claude Code | `claude --dangerously-skip-permissions` | `/permissions` |
| Gemini CLI | `gemini --yolo` | `/yolo` |
| Codex CLI | `codex --full-auto` | (session mode switch) |

If not in autonomous mode, the skill still runs but asks for permission at each step.

## Pipeline

The skill executes nine stages sequentially. Each stage is implemented by a helper script in `scripts/`.

| Stage | Helper | Purpose |
|-------|--------|---------|
| 0. PRECHECK | `scripts/precheck.py` | Environment + AI keys diagnosis |
| 1. SCOPE | `scripts/scope.py` | 5-question intake → `config.yaml` |
| 2. SCAFFOLD | `scripts/scaffold.py` | Directory + venv + installed deps + rendered templates |
| 3. AUTH | `scripts/auth_flow.py` | First-time login → `storage.json` |
| 4. RECORD | `scripts/record_flow.py` | Playwright codegen of download path |
| 5. REFACTOR | `scripts/refactor.py` | AI cleanup → `selectors.yaml` + `navigate.py` |
| 6. VALIDATE | `scripts/validate_loop.py` | Autonomous verify loop (max 5) |
| 7. APPROVE | `scripts/approve_flow.py` | Final user sign-off on sample data |
| 8. SCHEDULE | `scripts/schedule_install.py` | OS scheduler registration |
| 9. HANDOFF | `scripts/handoff.py` | Final README + summary |

## Harness-first execution

When the user's goal is to verify that UDD itself is working, use the
harness entrypoint instead of calling helper scripts ad hoc:

```bash
python "$SKILL_DIR/scripts/harness.py" new "$PROJECT_DIR"
python "$SKILL_DIR/scripts/harness.py" stage "$PROJECT_DIR" 3 --browser-channel chrome
python "$SKILL_DIR/scripts/harness.py" stage "$PROJECT_DIR" 5
python "$SKILL_DIR/scripts/harness.py" stage "$PROJECT_DIR" 6
python "$SKILL_DIR/scripts/harness.py" status "$PROJECT_DIR"
python "$SKILL_DIR/scripts/harness.py" audit "$PROJECT_DIR"
```

The harness writes `.udd/state.json` inside the project. Treat that file as the
source of truth for whether the skill actually ran. A generated downloader file
alone is not proof that UDD ran.

Rules for harness mode:
- Ask the harness intake questions before calling `harness.py new`; do not
  invent answers such as the schedule. The harness intake includes the original
  Stage 1 fields plus `site_type`:
  1. system slug
  2. URL
  3. site type (`authenticated_browser`, `public_browser_download`,
     `public_metadata_redirect`, `api`, or `static_file`)
  4. one-line description
  5. schedule
  6. expected columns
- If answers are supplied through an answers JSON file, state that this is a
  scripted intake and ensure the answers came from the user.
- Do not use `--no-install`, `--no-git`, or `--force` unless the user is
  explicitly testing a degraded/recovery path. These options are recorded in
  `.udd/state.json` and do not count as a normal full run.
- Do not manually rewrite generated files to make the outcome pass. If a manual
  patch is necessary, run `harness.py audit` and report that the run is no
  longer a clean UDD harness execution.
- For public metadata/API datasets, first capture that site type during intake;
  if the current helper pipeline cannot model it, stop and report the harness
  limitation instead of silently replacing Stage 3-6 with custom code.

## AI Provider Policy

Generated projects default to `healing.ai_provider: codex_cli`. Runtime
self-healing therefore calls the locally authenticated Codex CLI as a subprocess
instead of directly calling Anthropic, Gemini, or OpenAI APIs.

The runtime flow is:

```text
src/navigate.py find()
  -> all selectors fail
  -> src/healer.py captures compact/redacted DOM and optional screenshot
  -> src/llm_client.py runs `codex exec`
  -> JSON selector response is validated with Playwright
  -> selectors.yaml ai_discovered is updated
```

Windows note: call `codex.cmd`, not `codex.ps1`, because PowerShell execution
policy can block the `.ps1` shim. The generated client auto-detects
`%APPDATA%\npm\codex.cmd`, or you can set:

```yaml
healing:
  ai_provider: codex_cli
  codex_cli:
    command: "C:\\Users\\<user>\\AppData\\Roaming\\npm\\codex.cmd"
```

Direct external API providers are still available only when explicitly selected
with `healing.ai_provider: anthropic`, `gemini`, or `openai` and their API keys
are installed in the run environment.

## Execution

Invoke each stage in order via Bash. Example:

```bash
python "$SKILL_DIR/scripts/precheck.py"        # Stage 0
python "$SKILL_DIR/scripts/scope.py" "$PROJECT_DIR"
python "$SKILL_DIR/scripts/scaffold.py" "$PROJECT_DIR"
# … and so on through Stage 9
```

`$SKILL_DIR` = the skill bundle directory (e.g., `~/.claude/skills/udd`).
`$PROJECT_DIR` = target project directory (e.g., `~/ax-downloads/erp-sales`), created by Stage 2.

Full stage details follow in the sections below.

## Stage 0 — PRECHECK

Run `python $SKILL_DIR/scripts/precheck.py` and parse its JSON stdout.

Handling by status:
- `status=ok`: proceed to Stage 1.
- `status=missing`: the `missing` array lists what to install. Offer the user:
  - `playwright` missing → `pip install playwright`
  - `chromium` missing → `python -m playwright install chromium`
- `status=error`: `errors` array lists hard blockers (e.g., Python too old). Stop.

Also emit to the user:
- `autonomous_mode=false` → tell them to restart the CLI in autonomous mode (see table above).
- `ai_providers=[]` → warn that Stage 6 self-healing will be disabled; ask if they want to proceed anyway.

## Stage 1 — SCOPE

Ask the user five questions in order (one at a time):

1. System slug (lowercase-kebab)
2. Login URL
3. One-line description
4. Schedule (cron or natural language, e.g., "매일 09:00")
5. Expected columns (comma-separated; empty to skip)

In harness mode, also ask for `site_type` before the description. The raw
`scope.py` helper still accepts the original five lines; `harness.py` records
`site_type` in `config.yaml` and `.udd/state.json`.

Concatenate answers into a 5-line stdin payload and run:
```bash
printf "<ans1>\n<ans2>\n<ans3>\n<ans4>\n<ans5>\n" | \
  python $SKILL_DIR/scripts/scope.py $HOME/ax-downloads/<slug> --from-stdin
```
Confirm `config.yaml` is visible; offer the user a peek; ask if anything needs editing.

## Stage 2 — SCAFFOLD

```bash
python $SKILL_DIR/scripts/scaffold.py $PROJECT_DIR --skill-dir $SKILL_DIR
```
This creates the directory tree, renders all templates, creates `.venv`, installs requirements, installs Chromium, and runs `git init` + initial commit. Total time: 1–3 min depending on network.

## Stage 3 — AUTH + RECORD (combined first-time setup, recommended)

Tell the user: "A browser will open. Log in to the system, then navigate all the way to the data and click the download button. Close the browser when the file has downloaded."

```bash
python $SKILL_DIR/scripts/auth_flow.py $PROJECT_DIR --mode setup
```

If the bundled Chromium is rejected by the target site (some Korean
government / enterprise portals, e.g. data.go.kr, return ERR_CONNECTION_RESET
to Playwright's Chromium fingerprint), pass `--browser-channel chrome` to
use the system Chrome instead. This also writes to `auth.browser_channel` in
config.yaml so subsequent runs (verify, retrain, scheduled cron) stay
consistent.

```bash
python $SKILL_DIR/scripts/auth_flow.py $PROJECT_DIR --mode setup --browser-channel chrome
```

`--mode setup` runs a single Playwright codegen session that captures **both**
`auth/storage.json` (the session cookies/localStorage) **and**
`recordings/raw_recording.py` (the navigation+download click sequence). When
the user closes the browser, both artifacts are validated:

- Session is verified headlessly (load storage, hit URL, expect no login redirect).
- Recording is checked for `page.goto` + a download trigger (`expect_download` etc).

Exit codes:
- 0: setup complete (session + recording valid) → skip Stage 4, jump to Stage 5
- 1: storage missing OR session verification failed
- 2: recording missing
- 3: recording validation failed (no goto/download trigger detected) — re-run setup

If you already ran `--mode setup` once and only need to refresh one artifact,
use the lifecycle commands:
- `--mode save` → re-login only (storage refresh; used by `udd login`)
- Stage 4 (`record_flow.py`) → re-record only (used by `udd retrain`)

## Stage 4 — RECORD (retrain only — skip on first-time setup)

Use this stage only when:
- Stage 3 was run with `--mode save` (login-only) and you still need to record.
- The site UI changed and an existing project needs re-recording (`udd retrain`).

Tell the user: "The browser will open — this time already logged in. Navigate to the data you want, apply filters, click the download button. Close the browser when done."

```bash
python $SKILL_DIR/scripts/record_flow.py $PROJECT_DIR
```
Validates that the recording contains `page.goto` and a download-trigger pattern. If validation fails, offer to re-record.

## Stage 5 — REFACTOR

Calls `scripts/refactor.py` which uses the configured AI provider to refactor `recordings/raw_recording.py` into:
- `selectors.yaml` — named selector entries with primary + fallbacks
- `src/navigate.py` — `steps(page, config)` function using `find(page, "<name>")` calls
- `config.yaml` patches — hardcoded values → template variables

```bash
python $SKILL_DIR/scripts/refactor.py $PROJECT_DIR
```

Exit codes:
- 0: success
- 2: LLM call failed (check API key / rate limits / network)
- 3: LLM returned malformed JSON (rare; script retries once)
- 4: Generated code has syntax errors (retried once then gives up)

If exit != 0, surface the error to the user and offer to retry or fall back to manually editing selectors.yaml.

## Stage 6 — VALIDATE (autonomous loop)

```bash
python $SKILL_DIR/scripts/validate_loop.py $PROJECT_DIR
```

Reads JSON result from stdout:
- `status=success`: proceed to Stage 7
- `status=success_strict`: proceed to Stage 7 (with `--strict`)
- `status=escalate_logic`: diagnosis classified as code-level; tell the user the proposed fix, ask if they want to apply manually
- `status=escalate_no_patch`: LLM couldn't produce a usable patch; offer retrain
- `status=escalate_budget_exhausted`: 5 attempts exhausted; show last log + screenshots

In all escalate cases, send a telegram alert via `scripts/lib/telegram.py send()`.

## Stage 7 — APPROVE

```bash
python $SKILL_DIR/scripts/approve_flow.py $PROJECT_DIR
```

Displays the latest download to the user (path, shape, columns, head(10)) and sends a Telegram sample. Then ASK the user: "이 데이터가 맞나요? (YES / NO <reason>)".

- YES → proceed to Stage 8
- NO → feed the reason back into Stage 6 as an additional hint and rerun the loop

## Stage 8 — SCHEDULE

```bash
python $SKILL_DIR/scripts/schedule_install.py $PROJECT_DIR
```
Writes `{"ok": true}` on success. Reads `config.yaml.schedule.cron` and registers with the OS scheduler. Invoke `--uninstall` to remove.

## Stage 9 — HANDOFF

```bash
python $SKILL_DIR/scripts/handoff.py $PROJECT_DIR
```
Prints the final summary (project path, next run time, command cheatsheet). Also a good moment to send a Telegram "setup complete" message.

## Troubleshooting during skill run

- **Precheck fails** → offer to install missing pieces. If autonomous mode is on, just run the install command.
- **Stage 3 verification fails** → offer to retry `auth_flow.py` (user may have closed browser too early).
- **Stage 6 escalates** → show last attempt's JSON + screenshot to the user; ask if they want to retry, retrain, or abort.
- **Stage 7 NO** → treat the user's reason as a free-text diagnosis and rerun Stage 6 with that context.

## Resumption (skill re-invocation on existing project)

If the current working directory is inside `~/ax-downloads/<name>/` and a `config.yaml` exists, ask the user:
  1. Retrain (Stage 4 onwards)
  2. Re-login only
  3. Change schedule
  4. Just show status

Route accordingly instead of starting Stage 1 from scratch.
