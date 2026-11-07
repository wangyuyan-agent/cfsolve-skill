# cfapi 请求格式

`cfapi --profile FILE --spec FILE [--proxy-env NAME] [--out NEW_DIRECTORY]`

平台包中推荐经 `scripts/run.py cfapi` 调用，自动使用随包 profile。工具只使用显式代理；不继承 HTTP_PROXY、HTTPS_PROXY 或系统代理。

最小示例（域名必须换成当前授权目标）：

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

顶层字段：

| 字段 | 含义 |
| --- | --- |
| base_url | 必填，挑战入口及相对 path 的基准 |
| page_url | 发起业务请求的页面；缺省为 base_url。默认 Referer 只含其 origin，不泄露查询串 |
| clearance | `required`（默认）或 `none`；前者要求挑战页，后者不执行求解 |
| allowed_origins | 额外允许的业务请求 origin，默认只有 base_url 的 origin；可显式加入 API 子域 |
| cookies_file | 可选，完整 Set-Cookie 数组文件，只允许 clearance=none；相对路径基于 spec 所在目录 |
| min_interval_ms | 请求间最小间隔，默认 1000；不代表目标可接受的安全速率 |
| max_requests | 默认 20，超出则在发送前失败；按当前任务需要显式调整 |
| timeout_seconds | 单次 API 请求超时，默认 30；不控制上游整个挑战求解耗时 |
| max_response_bytes | 单个解码后响应上限，默认 4 MiB；超限停止 |
| requests | 非空数组；整批静态输入先校验再执行 |

每个请求：

- `method`：GET（默认）、POST、PUT、PATCH、DELETE、HEAD 或 OPTIONS。拼写错误会报错。
- `path` / `url`：二选一。path 必须以单个 `/` 开头，按 URL 规则解析；绝对 url 必须属于声明的 origin。
- `body`：JSON 值，包括数组、字符串、数字、布尔值和 null，默认 `application/json`。
- `raw_body`：原始字符串，与 body 互斥，必须设置 `content_type`。
- `headers`：字符串映射；同名字段忽略大小写后必须唯一。可显式覆盖默认 Origin/Referer/Accept-Language。
- `headers_env`：请求头名称 → 环境变量名；适合认证值。不可与 headers 中同名字段重复。
- `expect_status`：可选 HTTP 状态数组，默认接受 2xx。即使显式接受，429 和挑战响应仍停止。HTTP 预期符合不等于业务成功。
- `delay_ms`：请求前等待，与顶层间隔取较大值；第一个请求不等待。

Host、Content-Length、Transfer-Encoding、Connection、Cookie、User-Agent 和 Content-Type 不允许通过 headers 随意注入；分别由 URL、正文、Cookie jar、profile 和 content_type 决定。跨源请求默认不猜测 sec-fetch-site 的 same-site 关系；如果目标明确要求，可按真实页面关系显式设置。

跨源请求以及非 GET/HEAD 请求默认携带 page_url 的 Origin；同源 GET/HEAD 不自动添加。Origin/Referer 仍可按真实业务请求显式覆盖，每个字段只发送一个值。

表单与显式认证环境变量示例：

```json
{
  "method": "POST",
  "path": "/api/submit",
  "raw_body": "field=value",
  "content_type": "application/x-www-form-urlencoded",
  "headers_env": {"Authorization": "TASK_AUTHORIZATION"},
  "expect_status": [200, 201]
}
```

Cookie 文件是数组，每项为 `{"origin":"https://authorized-site.example/","set_cookie":"name=value; Domain=authorized-site.example; Path=/; Secure; HttpOnly"}`。保留真实属性，不扩大域/路径或去掉 Secure 来消除错误；过期或不合法 Cookie 会按 jar 规则拒绝。Cookie 文件应权限 0600。求解模式本身不导出、不重建 Cookie，因此保留原会话的所有属性与来源。

输出只含 index、method、status、expected_status、challenged、accepted、body_bytes、body_saved。没有 URL 查询串、认证值或正文。`--out` 必须指向不存在的目录，父目录必须已存在；保存文件按序号命名，不从 URL 派生文件名。错误保存或正文读取失败会停止，而不会假装成功。API 3xx 不自动跟随，非预期状态不重试；如需下一跳，应先核对作用域后明确添加请求。

批次内登录响应设置的 Cookie 可用于后续请求；从 JSON 正文得到的 Bearer token 不会自动提取或注入。若业务需要这种状态转换，应在明确授权的调用程序中处理，避免猜测协议。
