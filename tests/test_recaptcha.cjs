const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { parse, mint, proxyFromEnvironment } = require('../skill/cloudflare-bypass-cfsolve/scripts/mint_recaptcha_v3.cjs');

test('explicit target, key and action reach browser; token is private and never overwritten', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'cfsolve-v3-test-'));
  try {
    const output = path.join(directory, 'token');
    const options = parse(['--url', 'https://authorized-test.example/login', '--sitekey', 'test-key', '--action', 'login', '--output', output]);
    const calls = {};
    const page = { goto: async url => { calls.url = url; }, url: () => calls.url, waitForFunction: async () => {}, evaluate: async (_fn, args) => { calls.args = args; return 'LOCAL_DUMMY_TOKEN'; } };
    const chromium = { launch: async options => { calls.launch = options; return { newContext: async () => ({ newPage: async () => page }), close: async () => { calls.closed = true; } }; } };
    const result = await mint(options, chromium, {});
    assert.equal(calls.url, 'https://authorized-test.example/login');
    assert.deepEqual(calls.args, { sitekey: 'test-key', action: 'login' });
    assert.equal(calls.closed, true);
    assert.equal(calls.launch.chromiumSandbox, true);
    assert.equal(fs.readFileSync(output, 'utf8'), 'LOCAL_DUMMY_TOKEN\n');
    assert.equal(fs.statSync(output).mode & 0o777, 0o600);
    assert(!JSON.stringify(result).includes('LOCAL_DUMMY_TOKEN'));
    assert.throws(() => parse(['--url', calls.url, '--sitekey', 'test-key', '--action', 'login', '--output', output]));
  } finally { fs.rmSync(directory, { recursive: true }); }
});

test('missing target cannot fall back to a real site', () => {
  assert.throws(() => parse(['--sitekey', 'test-key', '--action', 'login', '--output', '/unused']));
  assert.throws(() => parse(['https://authorized-test.example', 'test-key', 'login']));
});

test('proxy is explicit and credentials are not left in its server URL', () => {
  assert.equal(proxyFromEnvironment({}, { HTTPS_PROXY: 'http://proxy.invalid' }), undefined);
  assert.deepEqual(proxyFromEnvironment({ '--proxy-env': 'TASK_PROXY' }, { TASK_PROXY: 'http://user:pass@127.0.0.1:8080' }), { server: 'http://127.0.0.1:8080', username: 'user', password: 'pass' });
});

test('browser is closed on page failure and no token is saved', async () => {
  let closed = false;
  const options = { '--url': 'https://authorized-test.example', '--output': '/unused' };
  const chromium = { launch: async () => ({ newContext: async () => ({ newPage: async () => ({ goto: async () => { throw new Error('test failure'); } }) }), close: async () => { closed = true; } }) };
  await assert.rejects(mint(options, chromium, {}));
  assert(closed);
});

for (const mode of ['ready-never-calls-back', 'execute-never-settles']) {
  test(`${mode} reaches deadline and closes browser`, async () => {
    let closed = false;
    const options = { '--url': 'https://authorized-test.example', '--sitekey': 'test-key', '--action': 'login', '--output': '/unused' };
    const page = { goto: async () => {}, url: () => options['--url'], waitForFunction: async () => {}, evaluate: async fn => {
      const vm = require('node:vm');
      const grecaptcha = { ready: callback => { if (mode !== 'ready-never-calls-back') callback(); }, execute: () => new Promise(() => {}) };
      return vm.runInNewContext(`(${fn.toString()})({sitekey:'test-key',action:'login'})`, { window: { grecaptcha } });
    } };
    const chromium = { launch: async () => ({ newContext: async () => ({ newPage: async () => page }), close: async () => { closed = true; } }) };
    await assert.rejects(mint(options, chromium, {}, 10), /timed out/);
    assert(closed);
  });
}
