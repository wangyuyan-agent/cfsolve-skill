//! 通用业务请求：保留客户端的传输和 Cookie 状态，单独构建唯一的 API 请求头。

use std::collections::BTreeMap;
use std::time::Duration;

use anyhow::{Context, Result, ensure};
use url::Url;
use wreq::header::{HeaderMap, HeaderName, HeaderValue};
use wreq::redirect::Policy;
use wreq::{Method, Response};

use super::BrowserClient;

pub struct ApiRequest<'a> {
    pub method: &'a str,
    pub url: &'a Url,
    pub page: &'a Url,
    pub body: Option<Vec<u8>>,
    pub content_type: Option<&'a str>,
    pub headers: &'a BTreeMap<String, String>,
    pub timeout: Duration,
}

fn headers(client: &BrowserClient, request: &ApiRequest<'_>) -> Result<HeaderMap> {
    let mut map = HeaderMap::new();
    // 只继承身份字段，不套用浏览器表单导航模板。
    for name in [
        "user-agent",
        "accept-language",
        "accept-encoding",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
    ] {
        if let Some(value) = client.own.get(name) {
            map.insert(HeaderName::from_bytes(name.as_bytes())?, value.clone());
        }
    }
    map.insert("accept", HeaderValue::from_static("*/*"));
    map.insert("sec-fetch-mode", HeaderValue::from_static("cors"));
    map.insert("sec-fetch-dest", HeaderValue::from_static("empty"));
    // 不猜测跨子域的 same-site 关系；只对严格同源情况补充此字段。
    if request.url.origin() == request.page.origin() {
        map.insert("sec-fetch-site", HeaderValue::from_static("same-origin"));
    }
    let origin = request.page.origin().ascii_serialization();
    if request.url.origin() != request.page.origin()
        || (request.method != "GET" && request.method != "HEAD")
    {
        map.insert("origin", HeaderValue::from_str(&origin)?);
    }
    // 默认只发送来源 origin，避免将页面 URL 的查询参数带到 API。
    map.insert("referer", HeaderValue::from_str(&format!("{origin}/"))?);
    if request.body.is_some() {
        map.insert(
            "content-type",
            HeaderValue::from_str(request.content_type.unwrap_or("application/json"))?,
        );
    }
    for (name, value) in request.headers {
        let key = HeaderName::from_bytes(name.as_bytes()).context("invalid header name")?;
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
            .contains(&key.as_str()),
            "header must be configured through its dedicated field or profile: {key}"
        );
        map.insert(
            key,
            HeaderValue::from_str(value).context("invalid header value")?,
        );
    }
    Ok(map)
}

pub async fn api_request(client: &BrowserClient, request: ApiRequest<'_>) -> Result<Response> {
    ensure!(
        ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"].contains(&request.method),
        "unsupported HTTP method"
    );
    ensure!(
        matches!(request.url.scheme(), "http" | "https"),
        "unsupported URL scheme"
    );
    let map = headers(client, &request)?;
    let method = Method::from_bytes(request.method.as_bytes())?;
    let mut builder = client
        .http
        .request(method, request.url.as_str())
        .default_headers(false)
        .headers(map)
        // API 重定向交给调用者显式处理，不自动重发业务请求或认证头。
        .redirect(Policy::none())
        .timeout(request.timeout);
    if let Some(body) = request.body {
        builder = builder.body(body);
    }
    Ok(builder.send().await?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fingerprint::Transport;
    use std::io::{BufRead, BufReader, Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::path::Path;
    use std::thread;

    fn client() -> BrowserClient {
        Transport::read(Path::new("profiles/safari-26-ios.json"))
            .unwrap()
            .client(None)
            .unwrap()
    }

    fn receive(stream: &mut TcpStream) -> String {
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut reader = BufReader::new(stream);
        let mut head = String::new();
        while !head.ends_with("\r\n\r\n") {
            assert_ne!(reader.read_line(&mut head).unwrap(), 0);
        }
        let length = head
            .lines()
            .filter_map(|s| s.split_once(':'))
            .find(|(k, _)| k.eq_ignore_ascii_case("content-length"))
            .map_or(0, |(_, v)| v.trim().parse::<usize>().unwrap());
        let mut body = vec![0; length];
        reader.read_exact(&mut body).unwrap();
        head.push_str(&String::from_utf8(body).unwrap());
        head
    }

    #[test]
    fn cross_origin_get_has_origin_and_same_origin_get_does_not() {
        let c = client();
        let url = Url::parse("https://api.example.test/data").unwrap();
        let page = Url::parse("https://page.example.test/form").unwrap();
        let custom = BTreeMap::new();
        let mut request = ApiRequest {
            method: "GET",
            url: &url,
            page: &page,
            body: None,
            content_type: None,
            headers: &custom,
            timeout: Duration::from_secs(5),
        };
        assert_eq!(
            headers(&c, &request).unwrap()["origin"],
            "https://page.example.test"
        );
        request.page = &url;
        assert!(!headers(&c, &request).unwrap().contains_key("origin"));
    }

    #[tokio::test]
    async fn json_headers_and_custom_origin_are_unique_on_the_wire() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = Url::parse(&format!("http://{}/api", listener.local_addr().unwrap())).unwrap();
        let task = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let message = receive(&mut stream);
            stream
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
                .unwrap();
            message
        });
        let custom = BTreeMap::from([
            ("Origin".into(), "https://page.example".into()),
            ("Accept-Language".into(), "zh-CN".into()),
        ]);
        let c = client();
        let response = api_request(
            &c,
            ApiRequest {
                method: "POST",
                url: &url,
                page: &Url::parse("https://page.example/form?private=1").unwrap(),
                body: Some(b"{\"x\":1}".to_vec()),
                content_type: Some("application/json"),
                headers: &custom,
                timeout: Duration::from_secs(5),
            },
        )
        .await
        .unwrap();
        assert!(response.status().is_success());
        let message = task.join().unwrap().to_ascii_lowercase();
        assert_eq!(message.matches("content-type:").count(), 1);
        assert!(message.contains("content-type: application/json\r\n"));
        assert_eq!(message.matches("\r\norigin:").count(), 1);
        assert!(message.contains("origin: https://page.example\r\n"));
        assert_eq!(message.matches("accept-language:").count(), 1);
        assert!(!message.contains("x-www-form-urlencoded"));
        assert!(!message.contains("navigate"));
        assert!(!message.contains("private=1"));
    }

    #[tokio::test]
    async fn options_stays_options_and_redirect_is_not_followed() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = Url::parse(&format!("http://{}/api", listener.local_addr().unwrap())).unwrap();
        let task = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let message = receive(&mut stream);
            stream.write_all(b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:1/never\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").unwrap();
            message
        });
        let c = client();
        let response = api_request(
            &c,
            ApiRequest {
                method: "OPTIONS",
                url: &url,
                page: &url,
                body: None,
                content_type: None,
                headers: &BTreeMap::new(),
                timeout: Duration::from_secs(5),
            },
        )
        .await
        .unwrap();
        assert_eq!(response.status().as_u16(), 302);
        assert!(task.join().unwrap().starts_with("OPTIONS /api "));
    }

    #[test]
    fn original_cookie_jar_keeps_domain_path_secure_and_host_only_scope() {
        let c = client();
        let origin = Url::parse("https://example.test/start").unwrap();
        c.add_cookie(
            "wide=1; Domain=example.test; Path=/; Secure; HttpOnly",
            &origin,
        );
        c.add_cookie("local=2; Path=/account; Secure", &origin);
        assert_eq!(
            c.cookies(&Url::parse("https://api.example.test/").unwrap())
                .len(),
            1
        );
        assert_eq!(
            c.cookies(&Url::parse("https://example.test/account/me").unwrap())
                .len(),
            2
        );
        assert!(
            c.cookies(&Url::parse("http://example.test/account/me").unwrap())
                .is_empty()
        );
        assert!(
            c.cookies(&Url::parse("https://other.test/").unwrap())
                .is_empty()
        );
        let wide = c.cookies(&origin).pop().unwrap();
        assert_eq!(wide.domain(), Some("example.test"));
        assert!(wide.secure());
        assert!(wide.http_only());
    }
}
