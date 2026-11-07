#!/usr/bin/env python3
"""解压已核验的本次构建包，验证入口并记录二进制运行库要求。"""
import argparse
import json
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from verify_package import verify

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    archives = list(args.artifacts.glob("cloudflare-bypass-cfsolve-*.tar.gz"))
    if len(archives) != 1:
        raise SystemExit("expected exactly one runtime package")
    archive = archives[0]
    verify(archive)
    report = {"archive": archive.name, "platform": platform.system(), "architecture": platform.machine(), "binaries": {}}
    with tempfile.TemporaryDirectory(prefix="cfsolve-smoke-") as temporary:
        with tarfile.open(archive) as tar:
            tar.extractall(temporary, filter="data")
        root = Path(temporary) / "cloudflare-bypass-cfsolve"
        for binary, flag in (("cfapi", "--version"), ("challenge", "--help")):
            subprocess.run([sys.executable, root / "scripts/run.py", binary, flag], check=True, capture_output=True)
            file = root / "bin" / binary
            data = file.read_bytes()
            if re.search(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/", data):
                raise SystemExit("unmapped build-user path in binary")
            item = {"launcher": "passed"}
            if platform.system() == "Linux":
                versions = set(x.decode() for x in re.findall(rb"GLIBC_(\d+\.\d+(?:\.\d+)?)", data))
                item["glibc_required"] = max(versions, key=lambda x: tuple(map(int, x.split('.'))))
                result = subprocess.run(["ldd", file], text=True, capture_output=True, check=True)
                if "not found" in result.stdout: raise SystemExit("missing runtime library")
                item["runtime_libraries"] = sorted(set(re.findall(r"^\s*(\S+)\s+=>", result.stdout, re.M)))
            else:
                result = subprocess.run(["otool", "-L", file], text=True, capture_output=True, check=True)
                item["runtime_libraries"] = [line.strip().split(' (')[0] for line in result.stdout.splitlines()[1:]]
            report["binaries"][binary] = item
    output = args.artifacts / "runtime-check.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output.read_text())

if __name__ == "__main__":
    main()
