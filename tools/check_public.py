#!/usr/bin/env python3
"""检查 Git 跟踪文件是否符合公开源码清单；只报告文件和规则，不打印匹配内容。"""
import re
import subprocess
from common import ROOT, load_lock
from package import SOURCE_FILES, RUNTIME_FILES

RULES = {
    "private-key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "github-token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "aws-access-key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "local-user-path": rb"/(?:Users|home)/[A-Za-z0-9_.-]+/",
    "private-network": rb"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
}

def main():
    runtime = "skill/cloudflare-bypass-cfsolve/"
    expected = set(SOURCE_FILES) | {runtime + x for x in (*RUNTIME_FILES, *load_lock()["profile_sha256"])}
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    tracked = {x for x in tracked if x}
    if tracked != expected:
        raise SystemExit("tracked files differ from explicit public source allowlist")
    failures = []
    for name in sorted(tracked):
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            failures.append((name, "link-or-missing"))
            continue
        data = path.read_bytes()
        failures.extend((name, rule) for rule, pattern in RULES.items() if re.search(pattern, data))
    if failures:
        for name, rule in failures: print(f"{name}: {rule}")
        raise SystemExit("public source check failed")
    print(f"Public source allowlist and pattern checks passed: {len(tracked)} files")

if __name__ == "__main__":
    main()
