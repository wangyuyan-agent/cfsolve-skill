# 可选 reCAPTCHA v3 辅助程序

它调用既有 Playwright/Chromium，在当前明确授权的页面执行普通 reCAPTCHA v3。没有 Enterprise、v2 或成功评分保证；它不代表服务端已接受 token。

```sh
umask 077
RUN_DIR="$(mktemp -d)"
node "$SKILL/scripts/mint_recaptcha_v3.cjs" \
  --url 'https://authorized-site.example/login' \
  --sitekey 'SITE_KEY_FROM_AUTHORIZED_PAGE' \
  --action 'login' \
  --output "$RUN_DIR/recaptcha-token.txt"
```

四个参数都必须提供，输出文件必须不存在，父目录需存在。文件以 0600 创建，stdout 只报告保存位置。使用页面已有的 grecaptcha；页面需要显式加载脚本时才加 `--load-script`。页面跨 origin 跳转会终止，需重新核对并显式提供最终页面。

默认使用可由 Node 解析的 `playwright`；可通过 PW_PATH 指向既有安装。CHROME_PATH 或 `--chrome` 可指定既有浏览器。工具不会安装依赖或下载浏览器，并显式启用 Chromium 沙箱（Playwright 默认关闭此选项）。Linux 下应使用支持沙箱的普通用户环境；root 或受限容器导致沙箱无法启动时直接失败，不自动添加 `--no-sandbox`，也不修改系统安全配置。

需要代理时使用 `--proxy-env TASK_BROWSER_PROXY`，不把凭据写进命令行或文档。Playwright 与 cfapi 支持的代理 scheme 有差异；本工具支持 HTTP/HTTPS 和无认证 SOCKS5，拒绝带认证的 SOCKS5。多阶段请求的实际出口应核验一致，不能因为变量名称相同就推断出口相同。

Google 规定 v3 token 有效期为两分钟，后端还会验证 action、hostname 和 score。应在实际业务动作前生成，按服务端结果验收。[Google 官方文档](https://developers.google.com/recaptcha/docs/v3)
