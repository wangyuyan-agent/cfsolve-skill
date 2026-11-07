# 固定版本与上游更新

维护入口是配套的 `cfsolve-skill-source` 源码包。运行时 skill 不应自行拉取 master 或替换自身二进制。

GitHub Actions 适合负责：检测上游 commit 变化、对固定版本运行离线回归、在不同 runner 构建平台包、生成摘要和保存构建产物。它不能替代指定目标的实际验收，也不应把未审查的新上游自动推到日常环境。

源码包含两个 workflow：

- `build.yml`：手动、PR 或 main 分支提交触发；固定 SHA 的官方 actions，最小只读权限。构建 Linux x64、Linux arm64、macOS arm64，跑 Rust 与回环 HTTP 测试，打包并核验，上传 workflow artifact。默认不创建 Release、不部署。
- `upstream-watch.yml`：每周或手动检查上游，写 Summary 和候选 JSON；不修改 lock、不自动合并。它随源码提供，尚未在任何仓库启用。

定时 workflow 需要放在默认分支；GitHub 的计划任务可能延迟，公开仓库长期没有活动时也可能被自动停用，因此保留手动触发入口。平台矩阵使用 GitHub 当前提供的 runner 标签，维护时按[官方 runner 清单](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)复核；调度限制见[官方 schedule 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

建议流程：发现新 commit → 独立分支核对差异 → 更新 lock、profile 和必要补丁 → PR 构建测试 → 对明确授权的测试目标验收 → 人工接纳并生成正式版本。需要自动 PR、发布或通知时，按目标仓库和可见范围另行配置；现有 workflow 不自带这些外发步骤。

哈希清单用于核对内容，不是数字签名，也不证明线上求解率。上游、Cargo.lock 和补丁固定使构建输入可追溯；编译器、系统工具及时间戳仍可能影响最终字节，不宣称不同环境构建必然逐字节相同。
