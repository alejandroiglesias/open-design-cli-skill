# Open Design CLI Recipes

Use this reference when the short workflow in `SKILL.md` is not enough.

## Source Checkout Invocation

For source checkouts, build the daemon and invoke the CLI script with Node:

```bash
corepack enable
pnpm install
pnpm --filter @open-design/daemon build

export OD_NODE_BIN="${OD_NODE_BIN:-$(command -v node)}"
export OD_BIN="${OD_BIN:-$PWD/apps/daemon/dist/cli.js}"
odc() { "$OD_NODE_BIN" "$OD_BIN" "$@"; }
```

Use `odc <command>` throughout these recipes. For packaged installs, replace `odc` with `od`.

## Headless Browser Verification

Generated artifact folders usually do not have their own Node dependencies. To let spawned agents run Playwright checks, expose the source checkout's e2e dependency folder before starting the daemon:

```bash
export NODE_PATH="$PWD/e2e/node_modules${NODE_PATH:+:$NODE_PATH}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/private/tmp/pw-browsers}"
pnpm --dir e2e exec playwright install chromium
OD_DATA_DIR="${OD_DATA_DIR:-$HOME/.open-design}" odc --no-open --port 7456
```

Ask the agent to use `@playwright/test`, not `playwright`, from the generated project directory:

```bash
node <<'NODE'
const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto('file://' + process.cwd() + '/index.html', { waitUntil: 'load' });
  const result = {
    title: await page.title(),
    h1: await page.locator('h1').first().innerText().catch(() => null),
    taskCount: await page.locator('.task').count().catch(() => 0),
  };
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})();
NODE
```

Make browser verification part of the generation prompt. Example: "After writing `index.html`, run a Playwright smoke check at desktop and mobile widths, inspect the DOM/screenshot for blank render, overlap, clipping, and broken interactions, make one improvement pass if needed, and report the checks." Open Design's default frontend flow self-reviews craft, but browser automation is only reliable when the prompt asks for it and the daemon inherits the browser-check environment variables.

If the machine does not have system Chrome, or if OD-spawned agents hit macOS Chrome Crashpad permission errors, use the Playwright-managed browser path above. If you explicitly want system Chrome, set `PLAYWRIGHT_CHROME_EXECUTABLE_PATH` and pass it as `executablePath` in the launch options:

```bash
export PLAYWRIGHT_CHROME_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

## Daemon And Data Directory

Start one daemon and point all clients at it:

```bash
OD_DATA_DIR="${OD_DATA_DIR:-$HOME/.open-design}" odc --no-open --port 7456
```

Check health:

```bash
curl -sS http://127.0.0.1:7456/api/health | jq .
odc daemon status --json
```

Stop a daemon:

```bash
odc daemon stop --daemon-url http://127.0.0.1:7456
```

If the app docs show `od://app`, use `http://127.0.0.1:7456` unless you know the current client resolves the custom scheme.

If `odc daemon start --headless --serve-web --port 7456` exits right after printing "listening", use the top-level `odc --no-open --port 7456` form.

## Project Run With Questions

Create the project:

```bash
PROJECT_JSON=$(odc project create \
  --name "Investor deck" \
  --skill frontend-design \
  --design-system apple \
  --json)
PROJECT_ID=$(jq -r '.project.id' <<<"$PROJECT_JSON")
CONV_ID=$(jq -r '.conversationId' <<<"$PROJECT_JSON")
```

Turn 1 asks:

```bash
odc run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "Create a 10-slide investor pitch for a SaaS for design teams." \
  --follow | tee od-run-1.ndjson
```

Extract an answer template:

```bash
python3 ~/.codex/skills/open-design-cli/scripts/extract_question_form.py od-run-1.ndjson --template > answers.txt
```

Edit `answers.txt`, then continue:

```bash
odc run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "$(cat answers.txt)" \
  --follow | tee od-run-2.ndjson
```

Read generated files:

```bash
odc files list "$PROJECT_ID"
odc files read "$PROJECT_ID" index.html > index.html
```

## Verify And Recover A Stalled Generation

Treat streamed text as provisional until the file API confirms an artifact exists:

```bash
RUN_ID=$(jq -r 'select(.event=="start") | .data.runId' od-run-2.ndjson | tail -n 1)
odc run info "$RUN_ID" --json | jq '{status, exitCode, signal, errorCode, error, eventsLogPath}'
odc files list "$PROJECT_ID" --json
```

Do not treat silence as failure by itself. Slow models may think for several minutes before producing an artifact. Wait for a conservative window such as 5-10 minutes, or longer for complex prompts, then compare stream output, run status, the event-log path from `run info`, and `odc files list "$PROJECT_ID"`. Only cancel if the run has claimed it is writing, or the run info/event log has stopped changing, and the files list is still empty or missing the expected artifact.

If those checks show no stream, status, event-log, or file activity, cancel and continue in the same project/conversation with a tighter instruction:

```bash
odc run cancel "$RUN_ID"
odc run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "The previous generation run stalled after planning and produced no files. Use the already-submitted form answers. Do not ask questions. Do not critique. Do not produce a long plan. Write a compact self-contained index.html now, under 220 lines. After writing, briefly state the file path." \
  --follow | tee od-run-recovery.ndjson
```

Then read, render, or inspect the artifact through the daemon:

```bash
odc files list "$PROJECT_ID" --json | jq '.files[] | {path,size,kind,artifactKind}'
odc files read "$PROJECT_ID" index.html > index.html
```

## Unattended Run

If the user explicitly wants no questions, say so in the prompt:

```bash
odc run start \
  --project "$PROJECT_ID" \
  --conversation "$CONV_ID" \
  --agent codex \
  --message "Do not ask follow-up questions or emit a question-form. Pick reasonable defaults and write index.html now. Design a polished task manager app." \
  --follow
```

Some API paths also honor `skipDiscoveryBrief: true` in project metadata.

## Scenario Plugin

The app docs may show:

```bash
odc run --plugin od-new-generation --prompt "..." --json --follow
```

If this checkout does not support that shorthand, use `odc project create` plus `odc run start --message`. When applying `od-new-generation`, the plugin requires inputs:

```bash
odc plugin apply od-new-generation \
  --inputs '{"artifactKind":"landing page","audience":"design teams","topic":"AI design workflows"}' \
  --json
```

## HTTP API Shapes

Create a project:

```bash
curl -sS -X POST http://127.0.0.1:7456/api/projects \
  -H 'content-type: application/json' \
  -d '{
    "id": "'"$(uuidgen | tr A-Z a-z)"'",
    "name": "Hermes test run",
    "metadata": { "kind": "prototype" },
    "pendingPrompt": "A landing page for an AI agent CLI",
    "pluginId": "od-new-generation"
  }' | jq .
```

List agents, skills, and design systems:

```bash
curl -sS http://127.0.0.1:7456/api/agents | jq '.agents[] | select(.available)'
curl -sS http://127.0.0.1:7456/api/skills | jq '.skills[0]'
curl -sS http://127.0.0.1:7456/api/design-systems | jq '.designSystems[0]'
```

## MCP Config

Use this in MCP-capable clients:

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

Ask the daemon for tailored install info when available:

```bash
curl -sS http://127.0.0.1:7456/api/mcp/install-info | jq .
```

## Troubleshooting

- `command -v od` returns `/usr/bin/od`: PATH is wrong; move the Open Design wrapper earlier.
- Source checkout on Unix-like systems: prefer `"$OD_NODE_BIN" "$OD_BIN"` or the `odc` helper instead of bare `od`.
- `od doctor` exits nonzero but daemon health is OK: inspect issue codes. Bundled registry/plugin doctor warnings may not block simple runs.
- `Cannot reach daemon`: start `od --no-open --port 7456`, or pass `--daemon-url http://127.0.0.1:<port>`.
- `Run finished but produced no files`: inspect the stream for `<question-form>` or tool/auth errors, then continue with form answers or fix the agent CLI.
- `od media generate` fails with provider errors: check the media provider config/API keys in the daemon environment.
