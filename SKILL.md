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

## Source Checkout Setup

For a source checkout, do not call bare `od` on Unix-like systems; it may resolve to the system octal-dump command. Build the daemon and invoke the built CLI script through Node:

```bash
git clone https://github.com/nexu-io/open-design.git
cd open-design
corepack enable
pnpm install
pnpm --filter @open-design/daemon build

export OD_NODE_BIN="${OD_NODE_BIN:-$(command -v node)}"
export OD_BIN="${OD_BIN:-$PWD/apps/daemon/dist/cli.js}"
odc() { "$OD_NODE_BIN" "$OD_BIN" "$@"; }

odc --help
```

If `corepack` is not on PATH, use a Node install that includes it. Open Design's repo expects pnpm `10.33.2` and a current Node runtime; Node 24 worked in validation.

For a packaged install or an intentional wrapper, `od <command>` is fine. For shareable automation, prefer the `odc` helper or explicit `"$OD_NODE_BIN" "$OD_BIN"` form.

## Enable Browser Checks

Open Design's generated project directories are usually plain artifact folders with no `node_modules`, so agents cannot assume `require('playwright')` works. Source checkouts include `@playwright/test` under `e2e/node_modules`; expose it before starting the daemon when the user wants headless browser verification:

```bash
export NODE_PATH="$PWD/e2e/node_modules${NODE_PATH:+:$NODE_PATH}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/private/tmp/pw-browsers}"
pnpm --dir e2e exec playwright install chromium
odc --port 7456 --no-open
```

Then instruct the agent to verify generated HTML with `@playwright/test` and `require`, not plain `playwright`. Prefer Playwright-managed Chromium for OD-spawned agents:

```bash
node <<'NODE'
const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto('file://' + process.cwd() + '/index.html');
  console.log(await page.title());
  console.log('tasks', await page.locator('.task').count());
  await browser.close();
})();
NODE
```

If you explicitly use system Chrome, set `PLAYWRIGHT_CHROME_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"` and pass it as `executablePath`. On macOS, OD-spawned agents may hit Chrome Crashpad permission errors with the system Chrome app; fall back to Playwright-managed Chromium by unsetting `PLAYWRIGHT_CHROME_EXECUTABLE_PATH`.

## First Checks

Verify the command and daemon before generating:

```bash
odc --help 2>/dev/null || od --help
odc --port 7456 --no-open
```

Run client commands from a second shell. In plain shell scripts, prefer `http://127.0.0.1:7456` over `od://app`; some packaged Open Design contexts resolve `od://app`, but ordinary `curl` usually does not.

```bash
curl -sS http://127.0.0.1:7456/api/health | jq .
odc status --json 2>/dev/null || odc daemon status --json
odc skills list --json | jq '.skills[0]'
odc design-systems list --json | jq '.designSystems[0]'
```

If `odc daemon start --headless --serve-web` prints that it is listening and then exits, use the top-level daemon form `odc --port 7456 --no-open` instead.

## Run A Design

Feature-detect the installed CLI shape:

```bash
odc run --help
```

If help shows `od run start`, use the project/run form:

```bash
PROJECT_JSON=$(odc project create \
  --name "Task manager" \
  --skill frontend-design \
  --design-system clean \
  --json)

PROJECT_ID=$(jq -r '.project.id' <<<"$PROJECT_JSON")
CONV_ID=$(jq -r '.conversationId' <<<"$PROJECT_JSON")

odc run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "Design a polished task manager app." \
  --follow | tee od-run.ndjson
```

If help supports the packaged shorthand from the app docs, this form may work:

```bash
odc run --plugin od-new-generation \
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
odc run start \
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
odc run info "$RUN_ID" --json | jq '{status, exitCode, signal, errorCode, error}'
odc files list "$PROJECT_ID" --json
```

If the stream says it is writing but `od files list` stays empty after a few minutes, cancel the stuck run and send a recovery turn in the same project/conversation:

```bash
odc run cancel "$RUN_ID"
odc run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "The previous run stalled and produced no files. Use the already-submitted form answers. Do not ask questions. Do not critique. Do not produce a long plan. Write a compact self-contained index.html now. After writing, state the file path." \
  --follow
```

## Read Outputs

List and read generated files through `od`:

```bash
odc files list "$PROJECT_ID"
odc files read "$PROJECT_ID" index.html > ./index.html
odc project info "$PROJECT_ID" | jq .
```

Project files usually live under the daemon data dir, for example `~/.local/share/open-design/.od/projects/<project-id>` or the configured `OD_DATA_DIR`.

## Other Surfaces

Use `od media generate` for direct image, video, or audio bytes:

```bash
odc media generate \
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
      "command": "node",
      "args": ["/absolute/path/to/open-design/apps/daemon/dist/cli.js", "mcp", "--daemon-url", "http://127.0.0.1:7456"],
      "env": { "OD_DATA_DIR": "~/.open-design" }
    }
  }
}
```

Read `references/cli-recipes.md` when you need more command examples, HTTP request shapes, or troubleshooting notes.
