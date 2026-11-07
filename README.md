# cfsolve 通用 skill 构建源码 · 3.0.1

这套维护源码把固定版本 [cfsolve](https://github.com/chris124567/cfsolve) 与通用请求封装组合起来，供自有或明确授权系统的自动化测试与研究使用。运行时入口在 [`skill/cloudflare-bypass-cfsolve/SKILL.md`](skill/cloudflare-bypass-cfsolve/SKILL.md)。

- cfsolve 负责 Cloudflare Turnstile／挑战页处理，`cfapi` 保留原客户端、指纹与 Cookie jar 发起明确指定的请求。
- 可选 reCAPTCHA v3 辅助程序通过 Playwright 调用页面 API，要求显式提供 URL、sitekey 和 action；它独立于 cfsolve，不保证评分或服务端接受。
- 测试使用回环 HTTP 服务及合成数据，不访问真实业务目标。风险与报告方式见 [SECURITY.md](SECURITY.md)。

构建要求：Python 3.12+、Git、固定 Rust 1.98.0、CMake、C/C++ 编译器及 libclang。可选浏览器辅助程序还需要 Node 20+ 与既有 Playwright/Chromium；不影响 cfsolve 核心工具。

```sh
python3 tools/prepare.py --dest .work/upstream
python3 tests/test_package.py
node --test tests/test_recaptcha.cjs
python3 tools/build.py --source .work/upstream
python3 tools/package.py --source .work/upstream --out artifacts
python3 tools/verify_package.py artifacts/cloudflare-bypass-cfsolve-v3.0.1-linux-x64.tar.gz
```

最后的文件名随当前平台变化。prepare 不覆盖已有目录；需重新准备时选新目录。build 会下载 Cargo 依赖，在同一固定源码上运行库测试、CLI 单元测试和回环 HTTP 回归，再编译 challenge 与 cfapi。release 构建保留 debug assertions，确保内部参数约定也受验证；Rust 和 C/C++ 编译会映射源码路径，减少分发二进制携带本机目录。构建记录写在源码工作目录，打包前重新检查源码和二进制摘要。

运行时包保留完整 profile、许可证、依赖许可索引、平台信息和文件 manifest；源码包包含本目录的构建工具、补丁、测试及 GitHub Actions 配置。平台二进制不能直接跨操作系统/架构使用；Linux glibc 基线取决于构建平台，不宣称 universal。

已有交叉编译环境时，可用 Cargo 标准变量 `CARGO_BUILD_TARGET` 指定 `x86_64-unknown-linux-gnu`、`aarch64-unknown-linux-gnu` 或 `aarch64-apple-darwin`。对应 Rust target、C/C++ linker、目标系统库和可执行目标二进制的环境须预先可用；构建工具仍实际运行测试和 CLI，不会因为只编译成功就生成通过记录。manifest 分别记录目标架构和构建主机架构。

`--out` 原始响应是用户显式选择保存的敏感调试材料，与发行包无关。不要将请求 spec、Cookie 文件、响应目录、账号材料或 `.work` 提交到维护仓库。

打包器按明确的发行文件清单选择源码和运行时资源，额外文件不会自动进入归档。新增辅助脚本或参考文档时，应同时更新 `tools/package.py` 的清单并检查交付内容。

## GitHub Actions

[构建与测试](https://github.com/wangyuyan-agent/cfsolve-skill/actions/workflows/build.yml) 在 main 推送、PR 或手动触发时，构建 Linux x64、Linux ARM64 和 macOS ARM64。Linux 使用 Ubuntu 22.04 runner，macOS 使用 macOS 15 runner。每个平台运行 Rust 库／CLI 测试、回环 HTTP 回归、归档检查和解压启动测试；reCAPTCHA 辅助流程另外在真实 Chromium 中访问本地合成页面。CI 安装锁定的 Playwright 测试依赖，运行时 skill 不自动安装浏览器。

[上游检测](https://github.com/wangyuyan-agent/cfsolve-skill/actions/workflows/upstream-watch.yml) 每周一 03:17 UTC 或手动执行，只生成 Summary 与候选 JSON；不会修改锁定版本、创建合并提交或发布 Release。计划任务可能延迟，公开仓库长期无活动时可能被 GitHub 停用。

两条 workflow 仅授予 `contents: read`，官方 actions 固定 commit SHA，checkout 不保留凭据。公开仓库的日志与 artifacts 不用于存放私密材料；构建产物保留 14 天，不自动发布 Release。源码备份远端只保存 Git 历史、不运行 CI；Git 同步不包含 Actions artifacts。

Linux 产物是 glibc 动态链接包，不能直接当作 Alpine/musl 包使用；实际 glibc 最低版本和动态库见每次 artifact 的 `runtime-check.json`。随包入口要求 Python 3.10+，构建及包烟测脚本使用 Python 3.12+。不同发行版仍需满足动态库要求，CI 通过不等于逐个发行版全部验收。macOS 包没有 Developer ID 签名或 Apple 公证，可能出现系统验证提示。

上游更新时先检查差异，更新 `upstream.lock.json` 的 revision、Rust 版本、Cargo.lock 与 profile 摘要，以及随包 profile，再在新目录 prepare。若补丁不能应用，停止并重做最小适配，不覆盖整份旧上游源文件。`tools/check_upstream.py --output .work/upstream-candidate.json` 只检查，不改变固定版本。旧版位置参数、gcapi 名称和 fetch/use_clearance 示例已收敛到 cfapi 的明确 schema。

本地测试不访问线上 Cloudflare 目标。CI 通过证明对应构建和回归通过，不等于当前所有站点可解。

3.0.1 保留上游 commit，通过受检补丁更新存在已知公告的兼容依赖版本。上游原始 Cargo.lock 和补丁后的 Cargo.lock 分别记录摘要；准备、构建和打包均核验对应版本。修复范围及仍保留的依赖事项见 [DEPENDENCIES.md](DEPENDENCIES.md)。
