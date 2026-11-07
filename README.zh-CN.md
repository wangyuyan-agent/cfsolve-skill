# cfsolve-skill

[English](README.md) | 简体中文

一套本地 CLI 工具和 Agent skill，用于在自有或明确授权的系统上测试 Cloudflare 挑战页、Turnstile 组件及验证后的 HTTP 请求。它基于固定版本的 [cfsolve](https://github.com/chris124567/cfsolve)，补充显式请求配置、会话复用和可核验的平台运行包。

**当前包版本：3.0.1。** 本仓库保存构建和维护源码。实际运行需下载对应平台的运行包，或按下文自行构建。仅从 GitHub 复制 `skill/cloudflare-bypass-cfsolve/` **不会安装二进制**。

## 这是什么工具

| 组件 | 用途 | 输出 |
| --- | --- | --- |
| `challenge` | 上游基于 HTTP 请求的 Cloudflare 求解器；该组件无需无头浏览器 | Turnstile token，或挑战页 clearance |
| `cfapi` | 本项目的 HTTP 批次封装；按需求解，再用原客户端、浏览器 profile 和 Cookie jar 调用 API | 逐请求 JSON 摘要；显式要求时才保存响应文件 |
| `scripts/run.py` | 识别运行平台的启动器 | 核验二进制摘要并选用随包 profile |
| `SKILL.md` | 给具备本地文件和 shell 能力的 Agent 使用 | 模式选择、请求配置、结果判断和失败处理 |
| `mint_recaptcha_v3.cjs` | 可选、独立的普通 reCAPTCHA v3 Playwright 辅助程序 | 将 token 保存到私有文件；不保证评分或接受结果 |

适合排查授权接口是否遇盾、复现通过挑战后的少量 API 请求，以及区分 CAPTCHA 验证和业务结果。skill 为 Agent 提供操作说明；它不是 MCP 服务，也不是托管的验证码服务。

## 获取可运行的包

打开 [Build pinned cfsolve skill](https://github.com/wangyuyan-agent/cfsolve-skill/actions/workflows/build.yml)，选择**目标提交对应的成功运行**，下载对应平台的 artifact。GitHub 可能要求登录。网页下载得到 ZIP，内含运行时 `.tar.gz`、对应 `.sha256`、源码归档和 `runtime-check.json`。

| 平台 | Actions artifact | 运行包后缀 | 运行要求 |
| --- | --- | --- | --- |
| Linux x86_64 | `cfsolve-skill-Linux-X64` | `linux-x64.tar.gz` | Python 3.10+、glibc 2.34+、`libgcc_s`、`libm`、`libstdc++`、libc |
| Linux ARM64 | `cfsolve-skill-Linux-ARM64` | `linux-arm64.tar.gz` | 同上，使用 ARM64 对应运行库 |
| macOS Apple Silicon | `cfsolve-skill-macOS-ARM64` | `darwin-arm64.tar.gz` | Python 3.10+；已在 macOS 15 ARM64 验证 |

上述 glibc 基线来自已验收的 3.0.1 构建；各次产物的实际依赖以 `runtime-check.json` 为准。当前没有经过验证的 Windows、Intel macOS 或 Alpine/musl 包。macOS 二进制没有 Developer ID 签名或 Apple 公证，可能出现系统验证提示。

Artifacts **保留 14 天**。项目不会自动发布 GitHub Release，也没有永久的“最新二进制”下载地址。产物过期后可从源码构建，维护者也可重新运行构建 workflow。[已验收的 3.0.1 构建](https://github.com/wangyuyan-agent/cfsolve-skill/actions/runs/42353362502)。

例如，使用已安装并登录的 GitHub CLI 下载该次 macOS 产物：

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

Linux 用户替换 artifact 和文件名，也可用 `sha256sum -c FILE.sha256` 校验。解压到新目录，保留完整包结构，包括 `profiles/`、`licenses/`、`manifest.json` 和两个二进制。校验和用于发现内容变化，不是发布者数字签名。源码仓库还提供 `python3 tools/verify_package.py /path/to/runtime.tar.gz`（Python 3.12+），可在解压前检查归档 manifest 和路径边界。

## 为 Agent 安装和调用 skill

先按上文解压、核验**运行包**，再把其中完整的 `cloudflare-bypass-cfsolve` 目录复制到 Agent 的 skill 搜索目录。不要只用通用 GitHub skill 安装器复制源码目录后就直接运行。

以 Codex 为例，保持 `SKILL` 指向解压后的运行目录：

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

如果目标已存在，复制会失败。升级时先在独立目录验证候选版本，保留能工作的旧安装，再替换。

- **Codex：** 用户级目录 `~/.agents/skills/`，或项目级 `.agents/skills/`；使用 `$cloudflare-bypass-cfsolve` 调用。参见 [Codex skill 发现规则](https://developers.openai.com/codex/skills/)。
- **Claude Code：** 将 `SKILLS_DIR` 改为 `~/.claude/skills/`，或使用项目级 `.claude/skills/`；使用 `/cloudflare-bypass-cfsolve` 调用。参见 [Claude Code skills](https://code.claude.com/docs/en/skills)。
- **Pi / OMP / 其他本地 Agent：** 将完整运行目录放入当前版本可发现的 skills 目录，或直接提供其中 `SKILL.md` 的绝对路径。保留相对文件结构。profile 或配置可能覆盖默认搜索路径，使用前确认 Agent 确实发现了该 skill。

新建会话，或使用对应 Agent 支持的 skill 重载命令。任务示例：

> 使用 cloudflare-bypass-cfsolve，检查我已授权的测试服务 https://authorized-site.example/ 的挑战模式，然后仅向 /api/account 发起一次 GET。再次遇盾、429 或非预期响应时停止。分别报告 HTTP 结果与业务结果，不在聊天中输出凭据或响应正文。

如果 Agent 不支持自动发现 skill：

> 读取 /absolute/path/cloudflare-bypass-cfsolve/SKILL.md，按其中流程使用启动器完成本次任务。授权目标是……；允许的请求是……；成功标准是……。

安装本身不会授权访问目标、安装 Playwright 或自动执行请求。Agent 仍需要兼容的本地运行环境和当前任务的具体目标、动作。

## 直接使用 CLI

### 挑战页 → API 请求

将以下内容保存为 `requests.json`，把示例 origin 和接口换成当前授权目标：

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

`required` 要求 `base_url` 存在挑战页；没有挑战或求解失败都会退出。普通 API 或显式导入 Cookie 的会话用 `"clearance": "none"`，此模式跳过求解。通过挑战后，批次继续使用原客户端和 Cookie jar，不导出 Cookie 再换一个 HTTP 客户端。

认证头可通过 `headers_env` 引用环境变量；JSON、表单、额外允许的 origin、Cookie 属性和输出限制见[请求格式](skill/cloudflare-bypass-cfsolve/references/request-schema.md)。默认最多 20 个请求、每次 API 请求超时 30 秒、单个解码后响应最多 4 MiB。该超时不限制上游整个挑战求解过程。

`cfapi` 默认直连，不继承 `HTTP_PROXY`、`HTTPS_PROXY` 或系统代理。需要显式代理时，传入环境变量名：

```sh
python3 "$SKILL/scripts/run.py" cfapi --spec ./requests.json --proxy-env TASK_PROXY
```

在执行环境中私下设置 `TASK_PROXY`。求解和后续 API 请求应保持实际出口 IP 与 profile 一致。

### 独立 Turnstile token

```sh
umask 077
RUN_DIR="$(mktemp -d)"
python3 "$SKILL/scripts/run.py" challenge \
  --page 'https://authorized-site.example/login' "$RUN_DIR/solve" \
  --solve --sitekey 'SITE_KEY_FROM_AUTHORIZED_PAGE' \
  > "$RUN_DIR/token.txt" 2> "$RUN_DIR/progress.log"
```

按页面真实配置补充 `--action`、`--cdata`。求解输出目录可能含原始请求和响应，应私下保存。token 必须按实际业务协议提交；`cfapi` 不会猜测插入位置。

### 可选 reCAPTCHA v3

需要 Node 20+、已安装的 Playwright 和 Chromium。它独立于 Cloudflare 求解器，不支持 reCAPTCHA v2 或 Enterprise。

```sh
umask 077
RUN_DIR="$(mktemp -d)"
node "$SKILL/scripts/mint_recaptcha_v3.cjs" \
  --url 'https://authorized-site.example/login' \
  --sitekey 'SITE_KEY_FROM_AUTHORIZED_PAGE' \
  --action 'login' \
  --output "$RUN_DIR/recaptcha-token.txt"
```

默认调用页面已有的 `grecaptcha`，显式开启 Chromium 沙箱；沙箱无法启动就失败，不自行安装浏览器或降级为 `--no-sandbox`。浏览器路径、代理和 token 验收见[辅助程序说明](skill/cloudflare-bypass-cfsolve/references/recaptcha-v3.md)。

### 判断结果

| `cfapi` 退出码 | 含义 |
| --- | --- |
| `0` | 所有请求符合声明的 HTTP 预期；仍需独立检查业务是否成功 |
| `2` | 非预期 HTTP 状态、再次遇盾或 HTTP 429；批次停止 |
| `1` | 配置、网络、读取或保存错误 |

默认按行输出 JSON：每次请求一条 `type: "response"` 记录，最后一条为带有 `completed` 的 `type: "batch"` 记录。应逐行解析 stdout，不应将其当作单个 JSON 文档。响应正文默认丢弃。确需检查原始响应时才加 `--out /path/to/new-directory`；父目录必须存在，目标目录必须不存在，输出使用私有权限。API 重定向不自动跟随，失败请求不自动重试。生成 token、服务端接受 CAPTCHA、业务动作完成需要分别验收。

## 优势与局限

- **本地、可检查：** Cloudflare 核心基于请求，不需要无头浏览器。源码、集成补丁、profile 和锁定依赖可审查；可选 reCAPTCHA 辅助程序有独立浏览器依赖。
- **会话连续：** `cfapi` 保留求解客户端及 Cookie 属性，显式声明请求范围、认证来源、正文大小和预期状态。
- **便于 Agent 使用：** 启动器和结构化摘要减少临时 shell 拼接、意外输出凭据及模糊的成功判断。
- **产物可追溯：** 平台检查、文件 manifest、许可证记录和三平台 CI 将运行包与受检构建输入关联起来。摘要不是发布者身份认证，也不保证跨环境逐字节可复现。
- **覆盖会失效：** Cloudflare 挑战会变化，服务端判断也不止依赖 Cookie。项目不承诺万能绕过、成功率指标或当前线上站点接受结果。随包 profile 为 iOS Safari 26，其记录的回答文件必须一起保留。
- **不编排未知业务：** 不自动登录、注册、发现目标、轮换身份／代理、从任意 JSON 提取 token 或重放失败的写请求。请求间隔不意味着目标允许这种流量。
- **仍有依赖事项：** `lru 0.16.3` 存在特定条件下的 panic-safety 公告，`smartstring 1.0.1` 已停止维护。已检查调用路径和覆盖限制见 [DEPENDENCIES.md](DEPENDENCIES.md)。CI 通过不等于安全审计通过。

## 构建与维护

构建要求：Python 3.12+、Git、Rust **1.98.0**、CMake、C/C++ 编译器和 libclang。辅助脚本测试需要 Node 20+，可选真实浏览器测试另需 Playwright/Chromium。构建会从相应上游下载依赖。

```sh
git clone https://github.com/wangyuyan-agent/cfsolve-skill.git
cd cfsolve-skill
python3 tools/prepare.py --dest .work/upstream
python3 tests/test_package.py
node --test tests/test_recaptcha.cjs
python3 tools/build.py --source .work/upstream
python3 tools/package.py --source .work/upstream --out artifacts
```

`prepare` 要求新目标目录。`build` 执行库测试、CLI 测试和回环 HTTP 回归，再编译两个工具；保留 debug assertions，并映射构建用户路径。`package` 核对源码与二进制摘要后，生成平台运行包和源码包。运行包使用前应通过 `tools/verify_package.py` 验证。

[构建 workflow](.github/workflows/build.yml) 在 main 推送、PR 或手动触发时构建 Linux x64、Linux ARM64、macOS ARM64，并用真实沙箱 Chromium 测试本地合成页面。测试不访问真实业务站点求解挑战。打包只纳入明确清单中的文件，新增发行资源需同步更新 `tools/package.py`。

[上游检测](.github/workflows/upstream-watch.yml) 每周一 03:17 UTC（北京时间 11:17）或手动运行，只生成 Summary 和候选 JSON，**不更新固定版本、不合并、不发布**。GitHub 调度可能延迟，也可能因长期无活动被停用。两条 workflow 采用只读 contents 权限及固定 SHA 的官方 actions。Git 源码备份不包含 Actions artifacts。

上游更新应先审查候选版本，适配补丁，更新 lock/profile 摘要，再准备新源码目录。使用 Cargo 标准变量交叉编译时，需具备对应 target、链接器、系统库以及真正运行目标测试的环境。详见[维护说明](skill/cloudflare-bypass-cfsolve/references/maintenance.md)。

## 参考与许可证

- [Agent 入口](skill/cloudflare-bypass-cfsolve/SKILL.md) · [请求格式](skill/cloudflare-bypass-cfsolve/references/request-schema.md) · [排障说明](skill/cloudflare-bypass-cfsolve/references/troubleshooting.md)
- [安全范围和报告方式](SECURITY.md) · [依赖记录](DEPENDENCIES.md)
- [上游 cfsolve](https://github.com/chris124567/cfsolve) 提供求解核心；本仓库提供集成、skill、打包和 CI。
- [MIT 许可证](LICENSE)。运行包包含上游与依赖的许可证记录。不要提交含秘密的请求配置、Cookie、token、原始响应或私有运行目录。
