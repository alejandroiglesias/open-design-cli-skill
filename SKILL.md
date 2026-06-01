---
name: open-design-cli
description: >-
  Use when Codex needs to drive Open Design from a terminal or another agent
  without relying on the UI: setting up or verifying the `od` command, starting
  the local daemon, running headless design generations, handling
  question-form discovery flows, reading generated project files, using
  `od media`, using the Open Design HTTP API, or configuring the Open Design MCP
  server.
---

# Open Design CLI

Use Open Design as a local daemon plus CLI. Prefer headless workflows unless the user explicitly asks to open the UI.

## First Checks

Verify the command and daemon before generating:

```bash
command -v od
od --help >/dev/null || od daemon --help
od --no-open --port 7456
```

Run client commands from a second shell. In plain shell scripts, prefer `http://127.0.0.1:7456` over `od://app`; some packaged Open Design contexts resolve `od://app`, but ordinary `curl` usually does not.

```bash
curl -sS http://127.0.0.1:7456/api/health | jq .
od status --json 2>/dev/null || od daemon status --json
od skills list --json | jq '.skills[0]'
od design-systems list --json | jq '.designSystems[0]'
```

If macOS resolves `/usr/bin/od`, the Open Design wrapper is not ahead of the system octal-dump command. Put the Open Design bin directory, often `~/.local/bin`, before `/usr/bin` in PATH.

## Run A Design

Feature-detect the installed CLI shape:

```bash
od run --help
```

If help shows `od run start`, use the project/run form:

```bash
PROJECT_JSON=$(od project create \
  --name "Task manager" \
  --skill frontend-design \
  --design-system clean \
  --json)

PROJECT_ID=$(jq -r '.project.id' <<<"$PROJECT_JSON")
CONV_ID=$(jq -r '.conversationId' <<<"$PROJECT_JSON")

od run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "Design a polished task manager app." \
  --follow | tee od-run.ndjson
```

If help supports the packaged shorthand from the app docs, this form may work:

```bash
od run --plugin od-new-generation \
  --prompt "A landing page for an AI agent CLI" \
  --json --follow
```

## Answer Question Forms

Open Design discovery is not `od ui respond` in current source checkouts. The first turn may emit a literal `<question-form id="discovery">...</question-form>` in the assistant text. Continue by sending another run message in the same project and conversation whose first line is:

```text
[form answers - discovery]
```

Then answer using the displayed question labels:

```bash
od run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message $'[form answers - discovery]\n- Who is this for?: busy solo founders\n- Product feel: Calm and minimal, Fast and focused\n- What should the mockup show?: Today task list, Project sidebar, Quick add task\n- Anything specific to include or avoid?: self-contained index.html, no external assets' \
  --follow
```

The daemon also accepts Unicode dash variants in the header, but prefer the ASCII hyphen for shell portability.

Use the bundled parser to extract the latest form and make an answer template from a saved run stream:

```bash
python3 <path-to-this-skill>/scripts/extract_question_form.py od-run.ndjson --template
```

When the user wants reliable generation, make the answer turn explicit: tell the agent to use the submitted answers, avoid asking more questions, write the artifact now, and state the file path when done.

## Verify And Recover

After every generation run, verify the daemon actually stored artifacts:

```bash
od run info "$RUN_ID" --json | jq '{status, exitCode, signal, errorCode, error}'
od files list "$PROJECT_ID" --json
```

If the stream says it is writing but `od files list` stays empty after a few minutes, cancel the stuck run and send a recovery turn in the same project/conversation:

```bash
od run cancel "$RUN_ID"
od run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "The previous run stalled and produced no files. Use the already-submitted form answers. Do not ask questions. Do not critique. Do not produce a long plan. Write a compact self-contained index.html now. After writing, state the file path." \
  --follow
```

## Read Outputs

List and read generated files through `od`:

```bash
od files list "$PROJECT_ID"
od files read "$PROJECT_ID" index.html > ./index.html
od project info "$PROJECT_ID" | jq .
```

Project files usually live under the daemon data dir, for example `~/.local/share/open-design/.od/projects/<project-id>` or the configured `OD_DATA_DIR`.

## Other Surfaces

Use `od media generate` for direct image, video, or audio bytes:

```bash
od media generate \
  --surface image \
  --model gpt-image-1 \
  --aspect 1:1 \
  --prompt "Editorial product shot, soft daylight, muted palette" \
  --output ./out/hero.png
```

Use HTTP when scripting around missing CLI sugar:

```bash
curl -sS http://127.0.0.1:7456/api/agents | jq '.agents[] | select(.available)'
curl -sS http://127.0.0.1:7456/api/projects | jq .
```

Use MCP when an agent should discover Open Design tools itself:

```json
{
  "mcpServers": {
    "open-design": {
      "command": "od",
      "args": ["mcp", "--daemon-url", "http://127.0.0.1:7456"],
      "env": { "OD_DATA_DIR": "~/.open-design" }
    }
  }
}
```

Read `references/cli-recipes.md` when you need more command examples, HTTP request shapes, or troubleshooting notes.
