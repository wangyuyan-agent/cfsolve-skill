# 排障与证据

先记录包版本、上游 revision、平台、当前授权操作和阶段。常规记录不包含 token、Cookie、密码、代理凭据或完整响应。

| 现象 | 优先检查 |
| --- | --- |
| cf-mitigated: challenge | Cloudflare 挑战页；不是目标 API 的正常业务响应 |
| 110200 | 官方客户端表为 Domain not authorized，先核对 sitekey 与嵌入 hostname；内部错误字段若映射未确认，应保留不确定性 |
| Unsupported | 可能是挑战版本、页面形态或参数不受支持，阅读具体阶段；不能直接断言 Cloudflare 换版 |
| clearance=required 失败 | 确认 base_url 当前确实有挑战；普通 API 用明确的 clearance=none，不自动切换 |
| Cookie 换客户端后失败 | 核对出口、profile、域/路径、Secure、有效期及实际请求；成功/失败差异不能独自证明 TLS 绑定机制 |
| 403 变为 401 | 说明响应路径变化，可能进入认证阶段；不能单独证明 Siteverify 成功或业务成功 |
| CLI 退出 0 | 仅说明已执行请求符合声明的 HTTP 状态预期；结合授权目标的业务响应验收 |

Cloudflare 更新、目标配置和会话行为均可能影响结果。没有通用成功率、稳定耗时、绝对安全频率或上游修复时限保证。对照测试应保持操作与输入条件一致；未验证、无盾、得到 token、后端接受、业务成功分别记录。

官方依据：[挑战响应检测](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/)、[Turnstile 错误码](https://developers.cloudflare.com/turnstile/troubleshooting/client-side-errors/error-codes/)、[Token 服务端校验](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)、[Clearance 生命周期](https://developers.cloudflare.com/cloudflare-challenges/concepts/clearance/)。
