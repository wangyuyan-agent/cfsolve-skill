# 依赖安全记录

2026-11-07 对固定 Cargo.lock 的 crates.io 条目及浏览器测试 npm 锁定依赖进行了 OSV 版本公告匹配。版本命中不等于已经证明当前调用路径可利用；没有命中也不证明不存在漏洞。修改过的 vendored crates、嵌套 BoringSSL C/C++ 源码和操作系统库不在此次版本匹配覆盖内。

## 3.0.1 定向更新

保留 cfsolve 上游 commit，不执行自动上游合并。只更新下列已锁定依赖到兼容修复版，完整变更保存在 `patches/integration.patch` 的 Cargo.lock 差异中。

| 依赖 | 版本变化 | 主要依据 |
|---|---|---|
| webpki-root-certs | 1.0.9 → 1.0.10 | [RUSTSEC-2026-0383](https://rustsec.org/advisories/RUSTSEC-2026-0383.html)：移除涉及不可信中间证书的根证书；此依赖用于当前 HTTPS 客户端 |
| tokio | 1.53.1 → 1.53.3 | [RUSTSEC-2026-0386](https://rustsec.org/advisories/RUSTSEC-2026-0386.html)：AsyncFd 的 I/O 安全 API 修正 |
| rand | 0.8.5 → 0.8.6 | [RUSTSEC-2026-0097](https://rustsec.org/advisories/RUSTSEC-2026-0097.html)：特定自定义日志器组合的重入问题 |
| lru | 0.16.2 → 0.16.3 | [RUSTSEC-2026-0002](https://rustsec.org/advisories/RUSTSEC-2026-0002.html)：修复 IterMut 内部引用问题 |
| zstd | 0.13.3 → 0.13.4；0.14.0 → 0.14.3 | [RUSTSEC-2026-0391](https://rustsec.org/advisories/RUSTSEC-2026-0391.html)：重用上下文时遗留前一条流的数据 |
| zstd-safe | 7.3.0 → 7.4.0；8.0.0 → 8.2.0 | RUSTSEC-2026-0395 至 0406：缓冲区、字典、上下文和旧格式流处理修复 |
| zstd-sys | 2.1.0 → 2.1.2 | [RUSTSEC-2026-0410](https://rustsec.org/advisories/RUSTSEC-2026-0410.html)：WebAssembly 分配器问题；本项目当前不构建 WebAssembly |

其中若干 API 问题需要特定功能或调用方式；依赖升级用于减少已知风险，不代表这些问题都能通过当前网络请求触发。

## 尚保留的事项

- **lru 0.16.3**：经 `swc_ecma_loader` 引入，仍命中 [RUSTSEC-2026-0253](https://rustsec.org/advisories/RUSTSEC-2026-0253.html)。该问题要求 `pop()` 时键的析构发生 panic，并结合展开／捕获继续使用缓存。已检查的调用方缓存键是 `(FileName, String)`，使用 get/put，未在该路径发现 pop 或 catch_unwind，尚未确认当前流程能触发。完全消除版本命中需适配超出该依赖版本约束的版本，留待上游依赖链更新；另一条 wreq 链使用 lru 0.18.4。
- **smartstring 1.0.1**：经 `swc_ecma_parser` 引入，命中 [RUSTSEC-2026-0249](https://rustsec.org/advisories/RUSTSEC-2026-0249.html) 的停止维护公告。这是维护风险提示，不是已确认的具体漏洞；不能只改锁文件替换其 API。

维护时重新查询公告与调用路径，不把本次记录视为持续有效的安全背书。CI 的功能测试和归档校验不能替代安全审查。
