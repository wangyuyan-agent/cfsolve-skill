#!/usr/bin/env node
// 可选的普通 reCAPTCHA v3 辅助程序；网址、sitekey、action 均由调用者显式提供。
const fs = require('node:fs');

function parse(argv) {
  const options = {};
  const fields = new Set(['--url', '--sitekey', '--action', '--output', '--proxy-env', '--chrome']);
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (key === '--load-script') {
      if (options.loadScript) throw new Error('duplicate --load-script');
      options.loadScript = true;
      continue;
    }
    if (!fields.has(key) || !argv[i + 1] || argv[i + 1].startsWith('--')) throw new Error('invalid arguments');
    if (options[key]) throw new Error('duplicate option');
    options[key] = argv[++i];
  }
  for (const key of ['--url', '--sitekey', '--action', '--output']) {
    if (!options[key]) throw new Error(`${key} is required`);
  }
  const url = new URL(options['--url']);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.hash) throw new Error('invalid page URL');
  if (!/^[A-Za-z0-9/_]+$/.test(options['--action'])) throw new Error('invalid reCAPTCHA action');
  if (fs.existsSync(options['--output'])) throw new Error('output already exists');
  return options;
}

function proxyFromEnvironment(options, env) {
  if (!options['--proxy-env']) return undefined;
  const value = env[options['--proxy-env']];
  if (!value) throw new Error('proxy environment variable is missing');
  const proxy = new URL(value);
  if (!['http:', 'https:', 'socks5:'].includes(proxy.protocol)) throw new Error('unsupported browser proxy scheme');
  if (proxy.protocol === 'socks5:' && (proxy.username || proxy.password)) throw new Error('authenticated SOCKS5 is unsupported by this helper');
  return { server: `${proxy.protocol}//${proxy.host}`, ...(proxy.username ? { username: decodeURIComponent(proxy.username), password: decodeURIComponent(proxy.password) } : {}) };
}

async function deadline(promise, milliseconds) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('token execution timed out')), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}

async function mint(options, chromium, env = process.env, executionTimeout = 30000) {
  const browser = await chromium.launch({ headless: true, executablePath: options['--chrome'] || env.CHROME_PATH || undefined, proxy: proxyFromEnvironment(options, env) });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(options['--url'], { waitUntil: 'domcontentloaded', timeout: 45000 });
    if (new URL(page.url()).origin !== new URL(options['--url']).origin) throw new Error('page redirected to a different origin; provide its explicit authorized URL');
    if (options.loadScript) {
      await page.addScriptTag({ url: `https://www.google.com/recaptcha/api.js?render=${encodeURIComponent(options['--sitekey'])}` });
    }
    await page.waitForFunction(() => window.grecaptcha && typeof window.grecaptcha.ready === 'function' && typeof window.grecaptcha.execute === 'function', null, { timeout: 30000 });
    const token = await deadline(page.evaluate(({ sitekey, action }) => new Promise((resolve, reject) => {
      window.grecaptcha.ready(() => window.grecaptcha.execute(sitekey, { action }).then(resolve, reject));
    }), { sitekey: options['--sitekey'], action: options['--action'] }), executionTimeout);
    if (typeof token !== 'string' || token.length === 0) throw new Error('empty token');
    fs.writeFileSync(options['--output'], token + '\n', { flag: 'wx', mode: 0o600 });
    return { saved: true, output: options['--output'] };
  } finally {
    await browser.close();
  }
}

async function main(argv) {
  if (argv.includes('--help')) {
    console.log('mint_recaptcha_v3.cjs --url URL --sitekey KEY --action ACTION --output NEW_FILE [--load-script] [--proxy-env NAME] [--chrome PATH]');
    return;
  }
  const options = parse(argv);
  // 只使用既有 Playwright 安装；不下载依赖或浏览器。
  const { chromium } = require(process.env.PW_PATH || 'playwright');
  console.log(JSON.stringify(await mint(options, chromium)));
}

module.exports = { parse, mint, proxyFromEnvironment };
if (require.main === module) {
  main(process.argv.slice(2)).catch(() => {
    // 浏览器错误可能携带目标 URL 或代理详情，默认只报告失败。
    console.error('reCAPTCHA helper failed; check arguments, page configuration and local browser installation');
    process.exitCode = 1;
  });
}
