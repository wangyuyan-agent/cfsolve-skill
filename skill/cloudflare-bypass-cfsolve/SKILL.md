---
name: cloudflare-bypass-cfsolve
description: 使用 cfsolve 调试明确授权的 Cloudflare 挑战页、Turnstile token 和求解后的 HTTP 会话复用。适用于请求级验证流程与失败诊断；附带可选的普通 reCAPTCHA v3 浏览器辅助程序。
license: MIT
metadata:
  version: 3.0.0
---

# cfsolve 通用工作流

本 skill 封装 [cfsolve](https://github.com/chris124567/cfsolve)。求解核心由上游提供；附加 `cfapi` 负责保留求解客户端、发送受控批次并输出结果摘要。它不会自动发现目标、登录、注册、发送验证码或执行历史台账中的任务。

以当前用户给出的目标、动作和授权范围为准。先确定页面属于挑战页、Turnstile widget，还是无需验证的普通 API；不要用单个状态码代替业务验收。

## 定位与运行

将 `SKILL` 设为本文件所在目录的绝对路径。用 Python 3.10+ 的 `scripts/run.py` 定位工具；它核对平台和二进制摘要，不自动下载或升级。

```sh
python3 "$SKILL/scripts/run.py" cfapi --help
python3 "$SKILL/scripts/run.py" cfapi --spec /absolute/path/requests.json
```

请求格式、跨域来源、敏感请求头、Cookie 导入和输出目录见 [references/request-schema.md](references/request-schema.md)。不要沿用旧版位置参数。

- `clearance: required`：先清除 `base_url` 的挑战页，然后用**原客户端及原 Cookie jar**执行批次。无挑战或求解失败就退出，不暗中切换流程。
- `clearance: none`：直接发送已定义的业务请求，用于无挑战页面或显式提供 Cookie 的会话。
- 保持求解与后续请求的出口和 profile 一致。默认直连；代理必须通过 `--proxy-env ENV_NAME` 显式传入，两阶段共同使用。不要把代理凭据放进命令参数。
- 挑战页与独立 Turnstile widget 是两种结果；`cfapi` 不会把 token 自动拼进未知业务协议。

## Turnstile token

使用上游 `challenge` 工具，并将结果写入私有工作目录。每轮使用新的求解子目录。

```sh
umask 077
RUN_DIR="$(mktemp -d)"
python3 "$SKILL/scripts/run.py" challenge \
  --page 'https://authorized-site.example/login' "$RUN_DIR/solve" \
  --solve --sitekey 'SITE_KEY_FROM_AUTHORIZED_PAGE' \
  > "$RUN_DIR/token.txt" 2> "$RUN_DIR/progress.log"
```

`--action`、`--cdata` 按页面真实配置设置；动态组件可结合 sitekey 使用 `--blank-page`，但这不保证任意站点接受。token 应及时随当前已授权的业务请求提交；生成 token、服务端验证成功和业务完成要分别报告。不要将 token、Cookie、密码或完整响应复制到技能文档或常规日志。

## 可选的 reCAPTCHA v3

仅当当前任务确实需要这种验证且环境已有 Playwright/Chromium 时，读取 [references/recaptcha-v3.md](references/recaptcha-v3.md)。它是独立浏览器流程，不属于 cfsolve 的求解能力；没有默认目标和默认 sitekey，不自动安装浏览器。

## 结果与失败

`cfapi` 默认只打印逐请求 JSON 摘要，不保存或打印响应正文。退出码 0 表示请求符合已声明的 HTTP 预期，**不证明业务成功**；2 表示非预期 HTTP 状态、再次遇盾或 429；1 表示配置、网络、读取或保存失败。

在非预期结果处停止批次，保留已发生动作的事实；不要自动重放 POST、换代理或更换身份。需要检查正文时显式指定新的 `--out` 目录，工具以目录 0700、文件 0600 保存。间隔参数仅控制节奏，没有通用的“不会触发风控”阈值。

Cloudflare 挑战响应首先看 `cf-mitigated: challenge`。`110200` 按官方文档先排查 hostname 授权；`Unsupported` 的原因可能包括新挑战版本，也可能是页面或配置不受支持。详细排障与证据要求见 [references/troubleshooting.md](references/troubleshooting.md)。

## 版本与维护

发行包的 `upstream.lock.json` 固定上游 commit，`manifest.json` 记录文件摘要和本次构建。平台包只含本平台可执行文件；源码包不含旧版二进制。

更新流程和 GitHub Actions 方案见 [references/maintenance.md](references/maintenance.md)。更新需在新候选版本上检查补丁、编译和回归；不直接覆盖已工作的安装，不把 CI 通过等同于线上挑战成功率验证。
