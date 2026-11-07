// 用真实浏览器访问回环测试页；模拟验证码 API，不请求 Google 或业务站点。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { once } = require('node:events');
const { chromium } = require('playwright');
const { parse, mint } = require('../../skill/cloudflare-bypass-cfsolve/scripts/mint_recaptcha_v3.cjs');

test('real Chromium preserves explicit inputs and private token output', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'cfsolve-browser-'));
  const server = http.createServer((request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html' });
    response.end('<script>window.grecaptcha={ready:cb=>cb(),execute:(key,{action})=>Promise.resolve("fixture:"+key+":"+action)}</script>');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try {
    const output = path.join(directory, 'token');
    const options = parse(['--url', `http://127.0.0.1:${server.address().port}/`, '--sitekey', 'fixture-key', '--action', 'test_action', '--output', output]);
    assert.equal((await mint(options, chromium, {})).saved, true);
    assert.equal(fs.readFileSync(output, 'utf8'), 'fixture:fixture-key:test_action\n');
    assert.equal(fs.statSync(output).mode & 0o777, 0o600);
  } finally {
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
