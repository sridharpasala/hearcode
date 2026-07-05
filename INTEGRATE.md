# Integrate your own agent

HearCode isn't Claude-Code-specific. Its entire integration surface is **one local
HTTP endpoint** the daemon exposes:

```
POST http://127.0.0.1:8420/event      # JSON body
```

Anything that can run a shell command or make an HTTP POST when your agent does
something — a hook, a tool wrapper, a CI step — can drive the soundtrack. Claude
Code's hooks are just one producer; the daemon doesn't know or care who's calling.

It's designed to be **fire-and-forget**: call it with a short timeout and ignore
the result (that's exactly what the Claude Code hook does:
`curl -sf --max-time 0.25 … || true`), so a stopped daemon never slows your agent
and a refused localhost connection fails instantly.

---

## The request

`POST /event` with a JSON object. Every field is optional except
`hook_event_name`; unknown fields are ignored.

| Field | Type | Purpose |
|-------|------|---------|
| `hook_event_name` | string | **The only required field.** The lifecycle event (table below). |
| `tool_name` | string | The tool the agent used — picks the per-tool leitmotif and the build/explore/action mood. |
| `tool_input` | object | Mined for a *target* fingerprint (which file/command) to detect stuck loops. |
| `tool_response` | object | Inspected for failure (`is_error` / `error` / `stderr`). |
| `tool_error` | any | Truthy ⇒ this event is a failure (the error sting fires). |
| `message` | string | Human-readable note spoken aloud on "needs you" alerts. |

### `hook_event_name` values

The name maps to a lifecycle family. **Anything not listed is ignored** (a no-op),
so the ~20 events you don't model never get misread as activity.

| `hook_event_name` | Effect |
|-------------------|--------|
| `PreToolUse` | A unit of work — drives intent (explore/build/action), intensity, and the tool's leitmotif. |
| `PostToolUse` | Tool finished — its outcome moves **build-health** when the tool was a test/build/lint. |
| `PostToolUseFailure` | Always treated as a **failure** (error sting; builds stuck-loop anxiety). |
| `Stop` / `SubagentStop` | The agent finished its turn — resolve chord, then silence. |
| `Notification` / `PermissionRequest` / `PermissionDenied` / `Elicitation` | The agent needs **you** — ducks the music, chimes, and speaks `message`. |
| `SessionStart` / `UserPromptSubmit` | A session began — start the soundtrack (explore). |
| *(anything else)* | Ignored — no effect on the music. |

### `tool_input` target keys

To spot the agent hammering the same thing (a doom loop), HearCode reads the first
present of these keys as the action's *target*:

```
file_path · path · notebook_path · command · pattern · url · query
```

So `{"tool_name":"Bash","tool_input":{"command":"pytest"}}` failing repeatedly
escalates anxiety faster than scattered failures.

### How a failure is detected

An event counts as an error if **any** of these hold:

- `hook_event_name` is `PostToolUseFailure`, or
- top-level `tool_error` is truthy, or
- `tool_response.is_error` / `.error` / `.tool_error` is truthy, or
- `tool_response.stderr` is a non-empty string.

---

## The response

`200 OK` with the current musical state — handy for debugging or building a
visualiser, and safe to ignore:

```json
{ "intent": "build", "intensity": 0.5, "anxiety": 0.0, "health": 0.8 }
```

`GET /health` returns `{"status": "ok"}` — use it to check the daemon is up.

### Control plane (read state / switch theme)

Two more endpoints let a UI (like the bundled macOS menu bar app) observe and
steer the running daemon without sending a fake event:

- **`GET /state`** — a read-only snapshot of the live mood plus the theme:

  ```json
  { "intent": "build", "intensity": 0.5, "anxiety": 0.0, "health": 0.8,
    "theme": "focus", "themes": ["focus", "uplift"], "voice": null }
  ```

- **`POST /theme`** `{"theme": "uplift"}` — switch the continuous bed **live**
  (seamless crossfade, no restart). Responds with `{"ok": true, "message": …}`
  merged with the `/state` snapshot; an unknown theme returns `"ok": false`.
- **`POST /voice`** `{"voice": "Daniel"}` — switch the spoken-alert voice (a
  macOS `say` voice name; `null`/`""` restores the system default). Same
  `{"ok", "message", …state}` response shape.

---

## Examples

Emulate a single tool call:

```bash
curl -sf -X POST http://127.0.0.1:8420/event \
  -d '{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"app.py"}}'
```

A whole tiny session — explore, a passing test, then done:

```bash
post() { curl -sf -X POST http://127.0.0.1:8420/event -d "$1" >/dev/null; }
post '{"hook_event_name":"SessionStart"}'
post '{"hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"app.py"}}'
post '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"pytest"}}'
post '{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"pytest"}}'
post '{"hook_event_name":"Stop"}'
```

Report a failure (fires the error sting, builds anxiety):

```bash
curl -sf -X POST http://127.0.0.1:8420/event \
  -d '{"hook_event_name":"PostToolUseFailure","tool_name":"Bash","tool_input":{"command":"pytest"},"tool_error":"exit status 1"}'
```

From a custom agent in Python — drop this into your tool-execution wrapper:

```python
import json, urllib.request

def hearcode(event, tool=None, tool_input=None, error=None):
    body = {"hook_event_name": event}
    if tool: body["tool_name"] = tool
    if tool_input: body["tool_input"] = tool_input
    if error: body["tool_error"] = str(error)
    req = urllib.request.Request(
        "http://127.0.0.1:8420/event",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=0.25)   # fire-and-forget
    except Exception:
        pass                                        # daemon down? never block the agent

# around each tool call:
hearcode("PreToolUse", tool="Edit", tool_input={"file_path": path})
# … run the tool …
hearcode("PostToolUse", tool="Edit", tool_input={"file_path": path})
# when the turn ends:
hearcode("Stop")
```

---

## Wiring it into different agents

- **Claude Code** — `hearcode install` merges the hooks into
  `~/.claude/settings.json` (or copy [`hooks.json`](hooks.json) yourself). Each
  hook just `curl`s its payload to the daemon.
- **Any hook-capable agent** (Cursor, etc.) — point a pre-/post-tool hook at the
  same one-line `curl` command. No HearCode code required.
- **Custom / SDK agents** — POST from your tool wrapper as shown above. The
  minimum useful set is `PreToolUse` on each call and a final `Stop`; add
  `PostToolUse` (with the command) to get build-health, and
  `PostToolUseFailure` to get error/stuck cues.

---

## Notes

- **Local only.** The daemon binds `127.0.0.1` — it never listens on the network.
- **Latency.** Keep a tight client timeout (`--max-time 0.25`) and swallow
  errors so a down daemon is a silent no-op on your hot path.
- **Port.** Override with `hearcode start --port N` (and pass the same `--port` to
  `hearcode install`); producers must target the same port.
- **What the daemon does with it** — how these events become music (the four
  dimensions: intent, intensity, anxiety, health) is described in the
  [README](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
