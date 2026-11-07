# cfsolve-skill

English | [简体中文](README.zh-CN.md)

A local CLI toolkit and agent skill for testing Cloudflare challenge pages, Turnstile widgets, and subsequent HTTP requests on systems you own or are authorized to test. Built around a pinned version of [cfsolve](https://github.com/chris124567/cfsolve), with explicit request specifications, session reuse, and verifiable platform packages.

**Current package version: 3.0.1.** This repository contains the build and maintenance source. To run the tools, download a matching platform package or build one below. Copying `skill/cloudflare-bypass-cfsolve/` from GitHub alone does **not** install the binaries.

## What it does

| Component | Purpose | Result |
| --- | --- | --- |
| `challenge` | Upstream request-based Cloudflare solver; no headless browser required for this component | A Turnstile token, or challenge-page clearance |
| `cfapi` | Our HTTP batch wrapper; solves a challenge when requested, then keeps the same client, browser profile, and cookie jar for API calls | Per-request JSON summaries; response files only when explicitly requested |
| `scripts/run.py` | Platform-aware launcher | Checks the binary digest and selects the bundled profile |
| `SKILL.md` | Instructions for a local agent with shell/file access | Mode selection, request setup, result interpretation, and failure handling |
| `mint_recaptcha_v3.cjs` | Optional, separate Playwright helper for ordinary reCAPTCHA v3 | A token saved to a private file; no score or acceptance guarantee |

Useful for investigating whether an authorized endpoint is challenged, reproducing a small API sequence after clearance, and checking the boundary between CAPTCHA validation and application behavior. The skill provides instructions to an agent; it is not an MCP server or hosted CAPTCHA service.

## Get a runnable package

Open [Build pinned cfsolve skill](https://github.com/wangyuyan-agent/cfsolve-skill/actions/workflows/build.yml), select a **successful run for the commit you intend to use**, and download the artifact for your platform. GitHub may require sign-in. The browser download is a ZIP containing the runtime `.tar.gz`, its `.sha256`, a source archive, and `runtime-check.json`.

| Platform | Actions artifact | Runtime archive suffix | Runtime requirements |
| --- | --- | --- | --- |
| Linux x86_64 | `cfsolve-skill-Linux-X64` | `linux-x64.tar.gz` | Python 3.10+, glibc 2.34+, `libgcc_s`, `libm`, `libstdc++`, libc |
| Linux ARM64 | `cfsolve-skill-Linux-ARM64` | `linux-arm64.tar.gz` | Same Linux requirements, ARM64 libraries |
| macOS Apple Silicon | `cfsolve-skill-macOS-ARM64` | `darwin-arm64.tar.gz` | Python 3.10+; tested on macOS 15 ARM64 |

The glibc baseline above was measured for the verified 3.0.1 build; inspect each artifact's `runtime-check.json` for its actual dependencies. Windows, Intel macOS, and Alpine/musl do not have a validated package here. macOS binaries are not Developer ID signed or notarized and may trigger system verification prompts.

Artifacts expire after **14 days**. There is no automatically published GitHub Release or permanent “latest binary” URL. If a package has expired, build from source; maintainers can also rerun the build workflow. [Verified 3.0.1 build](https://github.com/wangyuyan-agent/cfsolve-skill/actions/runs/42353362502).

For example, with an already installed and authenticated GitHub CLI, download that macOS artifact:

```sh
gh run download 42353362502 \
  --repo wangyuyan-agent/cfsolve-skill \
  --name cfsolve-skill-macOS-ARM64 \
  --dir cfsolve-download
cd cfsolve-download
shasum -a 256 -c cloudflare-bypass-cfsolve-v3.0.1-darwin-arm64.tar.gz.sha256
mkdir runtime
tar -xzf cloudflare-bypass-cfsolve-v3.0.1-darwin-arm64.tar.gz -C runtime
SKILL="$(pwd)/runtime/cloudflare-bypass-cfsolve"
python3 "$SKILL/scripts/run.py" cfapi --help
```

Use the matching artifact and archive names on Linux; `sha256sum -c FILE.sha256` is also available there. Extract into a new directory and keep the entire package together, including `profiles/`, `licenses/`, `manifest.json`, and both binaries. Checksums detect content changes; they are not publisher signatures. A source checkout also provides `python3 tools/verify_package.py /path/to/runtime.tar.gz` (Python 3.12+) to check the archive's manifest and path constraints before extraction.

## Install and use the agent skill

First unpack and check a **runtime package** as above. Then copy its complete `cloudflare-bypass-cfsolve` directory into your agent's skills location. Do not install the source-only directory using a generic GitHub skill installer and expect it to run.

For Codex, with `SKILL` still pointing to the unpacked runtime:

```sh
SKILLS_DIR="$HOME/.agents/skills"
python3 - "$SKILL" "$SKILLS_DIR" <<'PY'
from pathlib import Path
import shutil
import sys
source = Path(sys.argv[1]).resolve()
parent = Path(sys.argv[2]).expanduser()
parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, parent / "cloudflare-bypass-cfsolve")
PY
```

The copy fails if the destination already exists. For an upgrade, verify the candidate in a separate directory and preserve the working installation before replacing it.

- **Codex:** user-level `~/.agents/skills/`, or project-level `.agents/skills/`; invoke `$cloudflare-bypass-cfsolve`. See [Codex skill discovery](https://developers.openai.com/codex/skills/).
- **Claude Code:** use `~/.claude/skills/` as `SKILLS_DIR`, or project-level `.claude/skills/`; invoke `/cloudflare-bypass-cfsolve`. See [Claude Code skills](https://code.claude.com/docs/en/skills).
- **Pi / OMP / other local agents:** place the complete runtime in a skills directory discovered by your installed version, or give the agent the absolute path to its `SKILL.md`. Keep its relative files intact. Discovery paths can be overridden by profiles or configuration; confirm the skill appears in that agent before using it.

Start a new session or use your agent's supported skill reload command. Example task:

> Use cloudflare-bypass-cfsolve on my authorized test service at https://authorized-site.example/. Check the challenge mode, then make one GET to /api/account. Stop on a new challenge, 429, or unexpected response. Report HTTP results separately from application success; keep credentials and response bodies out of chat.

For agents without skill discovery:

> Read /absolute/path/cloudflare-bypass-cfsolve/SKILL.md and use its launcher for this task. The authorized target is …; allowed requests are …; success means ….

Installation does not grant target access, install Playwright, or automatically execute any requests. The agent still needs a compatible local runtime and the task's concrete target and action.

## Use the CLI directly

### Challenge page → API requests

Save the following as `requests.json`, replacing the example origin and endpoint with your authorized target:

```json
{
  "base_url": "https://authorized-site.example/",
  "page_url": "https://authorized-site.example/account",
  "clearance": "required",
  "min_interval_ms": 1000,
  "requests": [
    {"method": "GET", "path": "/api/account", "expect_status": [200]}
  ]
}
```

```sh
python3 "$SKILL/scripts/run.py" cfapi --spec ./requests.json
```

`required` expects a challenge at `base_url` and fails if none is present or solving fails. Use `"clearance": "none"` for a direct API request or explicitly imported cookies; this mode skips solving. The batch retains the original client and cookie jar after clearance instead of exporting a cookie and starting a different HTTP client.

Authentication headers can reference environment variables via `headers_env`; JSON bodies, forms, extra allowed origins, cookie attributes, and output limits are documented in the [request schema](skill/cloudflare-bypass-cfsolve/references/request-schema.md). Defaults include at most 20 requests, a 30-second timeout per API request, and a 4 MiB decoded response limit. That timeout does not bound the entire upstream challenge-solving process.

`cfapi` connects directly by default and does not inherit `HTTP_PROXY`, `HTTPS_PROXY`, or the system proxy. For an explicitly configured proxy, supply an environment variable name:

```sh
python3 "$SKILL/scripts/run.py" cfapi --spec ./requests.json --proxy-env TASK_PROXY
```

Set `TASK_PROXY` privately in your execution environment. Keep the actual exit IP and profile consistent across solving and API calls.

### Standalone Turnstile token

```sh
umask 077
RUN_DIR="$(mktemp -d)"
python3 "$SKILL/scripts/run.py" challenge \
  --page 'https://authorized-site.example/login' "$RUN_DIR/solve" \
  --solve --sitekey 'SITE_KEY_FROM_AUTHORIZED_PAGE' \
  > "$RUN_DIR/token.txt" 2> "$RUN_DIR/progress.log"
```

Use the page's actual `--action` and `--cdata` when needed. The solver's output directory can contain raw requests and responses: keep it private. A token must be submitted through the application's actual protocol; `cfapi` does not guess where to insert it.

### Optional reCAPTCHA v3

Requires Node 20+, an existing Playwright installation, and Chromium. This helper is separate from the Cloudflare solver and does not support reCAPTCHA v2 or Enterprise.

```sh
umask 077
RUN_DIR="$(mktemp -d)"
node "$SKILL/scripts/mint_recaptcha_v3.cjs" \
  --url 'https://authorized-site.example/login' \
  --sitekey 'SITE_KEY_FROM_AUTHORIZED_PAGE' \
  --action 'login' \
  --output "$RUN_DIR/recaptcha-token.txt"
```

It uses the page's existing `grecaptcha`, enables Chromium's sandbox, and fails if the sandbox cannot start. It does not install browsers or fall back to `--no-sandbox`. See [browser setup, proxies, and token validation](skill/cloudflare-bypass-cfsolve/references/recaptcha-v3.md).

### Interpret results

| `cfapi` exit code | Meaning |
| --- | --- |
| `0` | All requests met the declared HTTP expectations; application success still needs its own check |
| `2` | Unexpected HTTP status, a new challenge, or HTTP 429; the batch stops |
| `1` | Configuration, network, read, or save error |

By default, `cfapi` prints newline-delimited JSON: one `type: "response"` record per request, followed by a `type: "batch"` record with `completed`. Parse stdout line by line, not as one JSON document. Response bodies are discarded. Add `--out /path/to/new-directory` only when raw response inspection is needed; the parent must exist and the destination must not. Files are saved with private permissions. API redirects are not automatically followed, and failed requests are not retried. A generated token, server-side CAPTCHA acceptance, and a completed application action are separate outcomes.

## Advantages and limits

- **Local and inspectable:** the Cloudflare core uses requests rather than a headless browser. Source, integration patch, profile files, and pinned dependency inputs can be reviewed; the optional reCAPTCHA helper has its own browser dependency.
- **Session continuity:** `cfapi` keeps the solver's client and cookie attributes. Request scopes, authentication sources, body limits, and expected statuses are explicit.
- **Useful for agents:** a small launcher and structured summaries reduce shell glue, accidental secret printing, and ambiguous success reporting.
- **Traceable packages:** platform checks, file manifests, license records, and three-platform CI connect the runtime to the checked source inputs. Hashes do not establish a trusted publisher or guarantee bit-for-bit reproducible builds.
- **Coverage can break:** Cloudflare changes challenges and evaluates more than cookies. No universal bypass, success-rate benchmark, or current live-site acceptance guarantee is provided. The bundled profile is Safari 26 on iOS; its recorded answers must stay with the profile.
- **Not a business-workflow engine:** no automatic login/signup, target discovery, identity/proxy rotation, token extraction from arbitrary JSON, or automatic replay of failed writes. Request spacing is not a promise that a target permits the traffic.
- **Known dependency caveats remain:** `lru 0.16.3` has a conditional panic-safety advisory, and `smartstring 1.0.1` is unmaintained. See [DEPENDENCIES.md](DEPENDENCIES.md) for the checked call path and coverage limits. CI success is not a security audit.

## Build and maintain

Build prerequisites: Python 3.12+, Git, Rust **1.98.0**, CMake, a C/C++ compiler, and libclang. Node 20+ is needed for helper tests; the optional real-browser test additionally needs Playwright/Chromium. Build dependencies are downloaded from their respective upstream sources.

```sh
git clone https://github.com/wangyuyan-agent/cfsolve-skill.git
cd cfsolve-skill
python3 tools/prepare.py --dest .work/upstream
python3 tests/test_package.py
node --test tests/test_recaptcha.cjs
python3 tools/build.py --source .work/upstream
python3 tools/package.py --source .work/upstream --out artifacts
```

`prepare` requires a new destination. `build` runs library, CLI, and loopback HTTP tests before compiling both tools; it preserves debug assertions and remaps build-user paths. `package` checks source and binary digests, then emits a platform runtime archive and a source archive. Verify the runtime archive with `tools/verify_package.py` before use.

The [build workflow](.github/workflows/build.yml) runs on main pushes, pull requests, or manual dispatch for Linux x64, Linux ARM64, and macOS ARM64. It includes a real sandboxed Chromium test against a synthetic loopback page. Tests do not solve challenges on live business sites. Only explicitly allowlisted files enter packages; new distributable files must be added to `tools/package.py`.

The [upstream watcher](.github/workflows/upstream-watch.yml) runs on Mondays at 03:17 UTC and on manual dispatch. It writes a Summary and candidate JSON, **without updating pins, merging, or publishing**. Schedules may be delayed or disabled by GitHub after inactivity. Both workflows use read-only contents permissions and SHA-pinned official actions. Git source backups do not include Actions artifacts.

For an upstream update, review the candidate, adapt the patch, refresh the lock/profile digests, and prepare a fresh source directory. Standard Cargo cross-compilation variables are supported only with the required target toolchain, linker, libraries, and an environment capable of actually running the target tests. See [maintenance notes](skill/cloudflare-bypass-cfsolve/references/maintenance.md).

## References and license

- [Agent instructions](skill/cloudflare-bypass-cfsolve/SKILL.md) · [Request schema](skill/cloudflare-bypass-cfsolve/references/request-schema.md) · [Troubleshooting](skill/cloudflare-bypass-cfsolve/references/troubleshooting.md)
- [Security scope and reporting](SECURITY.md) · [Dependency record](DEPENDENCIES.md)
- [Upstream cfsolve](https://github.com/chris124567/cfsolve) provides the solver; this repository provides its integration, skill, packaging, and CI.
- [MIT license](LICENSE). Runtime archives include upstream and dependency license records. Never commit request specs containing secrets, cookies, tokens, raw responses, or private run directories.
