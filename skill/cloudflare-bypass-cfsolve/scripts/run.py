#!/usr/bin/env python3
"""从 skill 自身目录定位并核对当前平台二进制；不自动下载或更新。"""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("run.py {cfapi|challenge} [arguments]; cfapi uses --spec FILE")
        return 0
    command, *arguments = sys.argv[1:]
    if command not in ("cfapi", "challenge"):
        raise ValueError("unknown tool")
    manifest_path = ROOT / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("source-only skill: build a platform package using the accompanying source kit")
    manifest = json.loads(manifest_path.read_text())
    build = manifest["build"]
    arch = {"AMD64": "x86_64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
    expected = {"aarch64": "arm64"}.get(build["architecture"], build["architecture"])
    if platform.system().lower() != build["platform"] or arch != expected:
        raise ValueError("binary package does not match this OS/architecture")
    binary = ROOT / "bin" / command
    with binary.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()
    if actual != manifest["files"][f"bin/{command}"]:
        raise ValueError("binary checksum mismatch")
    flag = "--profile" if command == "cfapi" else "--fingerprint"
    if flag not in arguments and not any(x in arguments for x in ("--help", "-h", "--version")):
        arguments = [flag, str(ROOT / "profiles/safari-26-ios.json"), *arguments]
    return subprocess.run([str(binary), *arguments]).returncode

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as error:
        print(f"launcher: {error}", file=sys.stderr)
        sys.exit(1)
