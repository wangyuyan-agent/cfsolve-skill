//! 通用批处理入口；不输出正文或 Cookie，不自动重试业务请求。

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, DirBuilder, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Duration;

use anyhow::{Context, Result, bail, ensure};
use cfsolve::fingerprint::Transport;
use cfsolve::http::{ApiRequest, BrowserClient, api_request};
use cfsolve::{Browser, Options};
use http_body_util::BodyExt;
use serde::Deserialize;
use serde_json::{Value, json};
use url::Url;
use wreq::header::{HeaderName, HeaderValue};

const HELP: &str = "cfapi --profile FILE --spec FILE [--proxy-env NAME] [--out NEW_DIRECTORY]\n\
Outputs JSON summaries only. --out explicitly saves raw response bodies in a new private directory.\n\
See references/request-schema.md. No automatic retries or API redirects.";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Spec {
    base_url: String,
    page_url: Option<String>,
    #[serde(default)]
    allowed_origins: Vec<String>,
    #[serde(default)]
    clearance: ClearanceMode,
    cookies_file: Option<PathBuf>,
    #[serde(default = "interval")]
    min_interval_ms: u64,
    #[serde(default = "request_limit")]
    max_requests: usize,
    #[serde(default = "timeout")]
    timeout_seconds: u64,
    #[serde(default = "body_limit")]
    max_response_bytes: usize,
    requests: Vec<Request>,
}

fn interval() -> u64 {
    1000
}
fn request_limit() -> usize {
    20
}
fn timeout() -> u64 {
    30
}
fn body_limit() -> usize {
    4 * 1024 * 1024
}

#[derive(Default, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum ClearanceMode {
    #[default]
    Required,
    None,
}

fn explicit_json<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<Option<Value>, D::Error> {
    Value::deserialize(deserializer).map(Some)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    #[serde(default = "get")]
    method: String,
    path: Option<String>,
    url: Option<String>,
    #[serde(default, deserialize_with = "explicit_json")]
    body: Option<Value>,
    raw_body: Option<String>,
    content_type: Option<String>,
    #[serde(default)]
    headers: BTreeMap<String, String>,
    #[serde(default)]
    headers_env: BTreeMap<String, String>,
    expect_status: Option<Vec<u16>>,
    delay_ms: Option<u64>,
}
fn get() -> String {
    "GET".into()
}

struct Prepared {
    method: String,
    url: Url,
    body: Option<Vec<u8>>,
    content_type: Option<String>,
    headers: BTreeMap<String, String>,
    expect_status: Option<Vec<u16>>,
    delay_ms: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredCookie {
    origin: String,
    set_cookie: String,
}

fn url(text: &str) -> Result<Url> {
    let url = Url::parse(text).context("invalid URL")?;
    ensure!(
        matches!(url.scheme(), "http" | "https") && url.host_str().is_some(),
        "URL must use HTTP or HTTPS"
    );
    ensure!(
        url.username().is_empty() && url.password().is_none() && url.fragment().is_none(),
        "credentials and fragments are not allowed in URLs"
    );
    Ok(url)
}

fn allowed(spec: &Spec, base: &Url) -> Result<BTreeSet<String>> {
    let mut origins = BTreeSet::from([base.origin().ascii_serialization()]);
    for item in &spec.allowed_origins {
        let parsed = url(item)?;
        ensure!(
            parsed.path() == "/" && parsed.query().is_none(),
            "allowed_origins must contain origins, not paths or queries"
        );
        origins.insert(parsed.origin().ascii_serialization());
    }
    Ok(origins)
}

fn prepare(spec: &Spec, base: &Url, origins: &BTreeSet<String>) -> Result<Vec<Prepared>> {
    ensure!(
        !spec.requests.is_empty() && spec.requests.len() <= spec.max_requests,
        "empty batch or max_requests exceeded"
    );
    ensure!(
        spec.timeout_seconds > 0 && spec.max_response_bytes > 0,
        "timeout and response limit must be positive"
    );
    spec.requests
        .iter()
        .map(|r| {
            let method = r.method.to_ascii_uppercase();
            ensure!(
                ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
                    .contains(&method.as_str()),
                "unsupported HTTP method"
            );
            let target = match (&r.path, &r.url) {
                (Some(path), None) => {
                    ensure!(
                        path.starts_with('/') && !path.starts_with("//"),
                        "path must begin with a single slash"
                    );
                    url(base.join(path)?.as_str())?
                }
                (None, Some(value)) => url(value)?,
                _ => bail!("each request requires exactly one of path or url"),
            };
            ensure!(
                origins.contains(&target.origin().ascii_serialization()),
                "request origin is not in allowed_origins"
            );
            ensure!(
                !(r.body.is_some() && r.raw_body.is_some()),
                "body and raw_body are mutually exclusive"
            );
            let body = match (&r.body, &r.raw_body) {
                (Some(value), _) => Some(serde_json::to_vec(value)?),
                (_, Some(text)) => Some(text.as_bytes().to_vec()),
                _ => None,
            };
            ensure!(
                !(method == "HEAD" && body.is_some()),
                "HEAD request cannot have a body"
            );
            ensure!(
                r.raw_body.is_none() || r.content_type.is_some(),
                "raw_body requires content_type"
            );
            let content_type = r
                .content_type
                .clone()
                .or_else(|| r.body.as_ref().map(|_| "application/json".into()));
            if let Some(value) = &content_type {
                HeaderValue::from_str(value).context("invalid content_type")?;
            }
            let mut headers = BTreeMap::new();
            for (name, value) in &r.headers {
                add_header(&mut headers, name, value.clone())?;
            }
            for (name, env_name) in &r.headers_env {
                let value =
                    std::env::var(env_name).context("missing header environment variable")?;
                add_header(&mut headers, name, value)?;
            }
            if let Some(statuses) = &r.expect_status {
                ensure!(
                    !statuses.is_empty() && statuses.iter().all(|s| (100..=599).contains(s)),
                    "invalid expect_status"
                );
            }
            Ok(Prepared {
                method,
                url: target,
                body,
                content_type,
                headers,
                expect_status: r.expect_status.clone(),
                delay_ms: r.delay_ms.unwrap_or(0).max(spec.min_interval_ms),
            })
        })
        .collect()
}

fn add_header(headers: &mut BTreeMap<String, String>, name: &str, value: String) -> Result<()> {
    let name = HeaderName::from_bytes(name.as_bytes())
        .context("invalid header name")?
        .as_str()
        .to_owned();
    ensure!(
        ![
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "cookie",
            "user-agent",
            "content-type"
        ]
        .contains(&name.as_str()),
        "use dedicated field or profile for reserved header"
    );
    HeaderValue::from_str(&value).context("invalid header value")?;
    ensure!(
        headers.insert(name, value).is_none(),
        "duplicate header name (case-insensitive)"
    );
    Ok(())
}

fn private_directory(path: &Path) -> Result<()> {
    let mut builder = DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder
        .create(path)
        .context("output directory must be new and its parent must exist")
}

fn save_body(directory: &Path, index: usize, body: &[u8]) -> Result<()> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(directory.join(format!("{index:04}.body")))?;
    file.write_all(body)?;
    Ok(())
}

async fn batch(
    client: &BrowserClient,
    page: &Url,
    spec: &Spec,
    prepared: Vec<Prepared>,
    out: Option<&Path>,
) -> Result<bool> {
    for (index, request) in prepared.into_iter().enumerate() {
        // 请求间隔仅是节奏控制，不代表对目标而言一定安全。
        if index > 0 {
            tokio::time::sleep(Duration::from_millis(request.delay_ms)).await;
        }
        let mut response = api_request(
            client,
            ApiRequest {
                method: &request.method,
                url: &request.url,
                page,
                body: request.body,
                content_type: request.content_type.as_deref(),
                headers: &request.headers,
                timeout: Duration::from_secs(spec.timeout_seconds),
            },
        )
        .await
        .map_err(|_| anyhow::anyhow!("API transport failed; batch stopped without retry"))?;
        let status = response.status().as_u16();
        let challenged = response
            .headers()
            .get("cf-mitigated")
            .is_some_and(|v| v.as_bytes() == b"challenge");
        let expected = request
            .expect_status
            .as_ref()
            .map_or((200..300).contains(&status), |s| s.contains(&status));
        let mut body = Vec::new();
        while let Some(frame) = response.frame().await {
            let frame =
                frame.map_err(|_| anyhow::anyhow!("response body read failed; batch stopped"))?;
            if let Ok(chunk) = frame.into_data() {
                ensure!(
                    body.len().saturating_add(chunk.len()) <= spec.max_response_bytes,
                    "response exceeds max_response_bytes; batch stopped"
                );
                body.extend_from_slice(&chunk);
            }
        }
        if let Some(directory) = out {
            save_body(directory, index, &body)
                .context("cannot save response body; batch stopped")?;
        }
        let accepted = expected && !challenged && status != 429;
        println!(
            "{}",
            json!({"type":"response", "index":index, "method":request.method, "status":status, "expected_status":expected, "challenged":challenged, "accepted":accepted, "body_bytes":body.len(), "body_saved":out.is_some()})
        );
        if !accepted {
            return Ok(false);
        }
    }
    Ok(true)
}

async fn run() -> Result<bool> {
    let mut args = std::env::args().skip(1);
    let (mut profile, mut spec_path, mut proxy_env, mut out) = (None, None, None, None);
    while let Some(arg) = args.next() {
        let slot = match arg.as_str() {
            "--help" | "-h" => {
                println!("{HELP}");
                return Ok(true);
            }
            "--version" => {
                println!("cfapi skill 3.0.0");
                return Ok(true);
            }
            "--profile" => &mut profile,
            "--spec" => &mut spec_path,
            "--proxy-env" => &mut proxy_env,
            "--out" => &mut out,
            _ => bail!("unknown CLI argument; use --help"),
        };
        ensure!(slot.is_none(), "duplicate CLI option");
        *slot = Some(args.next().context("missing CLI argument value")?);
    }
    let profile = profile.context("--profile is required")?;
    let spec_path = PathBuf::from(spec_path.context("--spec is required")?);
    let spec: Spec = serde_json::from_slice(&fs::read(&spec_path).context("cannot read spec")?)
        .context("invalid spec")?;
    let base = url(&spec.base_url)?;
    let page = url(spec.page_url.as_deref().unwrap_or(&spec.base_url))?;
    let origins = allowed(&spec, &base)?;
    let prepared = prepare(&spec, &base, &origins)?;
    let proxy = proxy_env
        .map(|name| std::env::var(name).context("missing proxy environment variable"))
        .transpose()?;
    let cookies: Vec<StoredCookie> = if let Some(path) = &spec.cookies_file {
        ensure!(
            spec.clearance == ClearanceMode::None,
            "cookies_file requires clearance=none"
        );
        let path = spec_path.parent().unwrap_or(Path::new(".")).join(path);
        serde_json::from_slice(&fs::read(path).context("cannot read cookies_file")?)
            .context("invalid cookies_file")?
    } else {
        Vec::new()
    };
    for cookie in &cookies {
        ensure!(
            origins.contains(&url(&cookie.origin)?.origin().ascii_serialization()),
            "cookie origin is not allowed"
        );
    }
    // 所有静态输入先校验，再创建输出和发起网络请求。
    if let Some(path) = &out {
        private_directory(Path::new(path))?;
    }
    let client = match spec.clearance {
        ClearanceMode::Required => {
            Browser::read(&profile).context("invalid browser profile")?
                .clear_session(&base, &Options { proxy: proxy.clone(), sink: None }).await
                .map_err(|_| anyhow::anyhow!("clearance solve failed; no business requests sent (use clearance=none only when appropriate)"))?
        }
        ClearanceMode::None => Transport::read(Path::new(&profile))?.client(proxy.as_deref()).context("cannot create HTTP client")?,
    };
    for cookie in &cookies {
        client.add_cookie(&cookie.set_cookie, &url(&cookie.origin)?);
    }
    let completed = batch(
        &client,
        &page,
        &spec,
        prepared,
        out.as_deref().map(Path::new),
    )
    .await?;
    println!("{}", json!({"type":"batch", "completed":completed}));
    Ok(completed)
}

#[tokio::main]
async fn main() {
    let status = match run().await {
        Ok(true) => 0,
        Ok(false) => 2,
        Err(error) => {
            // 不打印底层错误链，避免 URL、代理凭据或响应内容出现在日志。
            eprintln!("{}", json!({"type":"error", "message":error.to_string()}));
            1
        }
    };
    std::process::exit(status);
}

#[cfg(test)]
mod tests {
    use super::*;
    fn parse(requests: Value) -> Spec {
        serde_json::from_value(json!({"base_url":"https://example.test/root/", "clearance":"none", "requests":requests})).unwrap()
    }
    #[test]
    fn invalid_later_request_is_rejected_before_execution() {
        let spec = parse(json!([{"path":"/ok"},{"method":"TYPO","path":"/no"}]));
        let base = url(&spec.base_url).unwrap();
        assert!(prepare(&spec, &base, &allowed(&spec, &base).unwrap()).is_err());
    }
    #[test]
    fn paths_json_scalars_and_null_are_preserved() {
        let spec = parse(
            json!([{"method":"POST","path":"/api","body":false},{"method":"POST","path":"/api","body":null}]),
        );
        let base = url(&spec.base_url).unwrap();
        let prepared = prepare(&spec, &base, &allowed(&spec, &base).unwrap()).unwrap();
        assert_eq!(prepared[0].url.as_str(), "https://example.test/api");
        assert_eq!(prepared[0].body.as_deref(), Some(b"false".as_slice()));
        assert_eq!(prepared[1].body.as_deref(), Some(b"null".as_slice()));
    }
    #[test]
    fn undeclared_origins_and_case_duplicate_headers_are_rejected() {
        for requests in [
            json!([{"url":"https://other.test/api"}]),
            json!([{"path":"/api","headers":{"X-Test":"one","x-test":"two"}}]),
        ] {
            let spec = parse(requests);
            let base = url(&spec.base_url).unwrap();
            assert!(prepare(&spec, &base, &allowed(&spec, &base).unwrap()).is_err());
        }
    }
}
