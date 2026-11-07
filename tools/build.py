#!/usr/bin/env python3
"""测试和编译同一份固定源码，生成由打包器检查的构建记录。"""
import argparse
import datetime
import json
import os
import platform
import shlex
import subprocess
from pathlib import Path
from common import ROOT, input_digest, load_lock, run, sha256, validate_tree

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = validate_tree(args.source)
    lock = load_lock()
    target = os.environ.get("CARGO_BUILD_TARGET")
    target_platforms = {"x86_64-unknown-linux-gnu": ("linux", "x86_64"), "aarch64-unknown-linux-gnu": ("linux", "aarch64"), "aarch64-apple-darwin": ("darwin", "arm64")}
    if target and target not in target_platforms:
        raise SystemExit("unsupported package target")
    package_platform, package_arch = target_platforms[target] if target else (platform.system().lower(), platform.machine())
    binary_directory = source / "target" / (target or "") / "release"
    rust = subprocess.check_output(["rustc", "--version"], cwd=source, text=True).strip()
    if rust.split()[1] != lock["rust_toolchain"]:
        raise SystemExit("rustc does not match pinned toolchain")
    before = input_digest()
    metadata = subprocess.check_output(["cargo", "metadata", "--locked", "--format-version=1"], cwd=source)
    (source / "dependencies.json").write_bytes(metadata)
    env = dict(os.environ, CARGO_PROFILE_RELEASE_DEBUG_ASSERTIONS="true")
    # 编译器路径映射避免将维护者用户名和本机目录嵌入分发二进制。
    flags = env.get("CARGO_ENCODED_RUSTFLAGS", "").split("\x1f") if env.get("CARGO_ENCODED_RUSTFLAGS") else shlex.split(env.get("RUSTFLAGS", ""))
    cargo_home = Path(env.get("CARGO_HOME", Path.home() / ".cargo")).resolve()
    flags += [f"--remap-path-prefix={Path.home()}=/build-user", f"--remap-path-prefix={source}=/cfsolve", f"--remap-path-prefix={cargo_home}=/cargo"]
    env["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(flags)
    env.pop("RUSTFLAGS", None)
    for key in ("CFLAGS", "CXXFLAGS"):
        env[key] = shlex.join([*shlex.split(env.get(key, "")), f"-ffile-prefix-map={source}=/cfsolve", f"-ffile-prefix-map={cargo_home}=/cargo"])
    run(["cargo", "test", "--locked", "--release", "--lib", "--", "--test-threads=1"], source, env)
    run(["cargo", "test", "--locked", "--release", "--example", "cfapi"], source, env)
    run(["cargo", "build", "--locked", "--release", "--example", "cfapi", "--bin", "challenge"], source, env)
    binary = binary_directory / "examples/cfapi"
    run(["python3", ROOT / "tests/test_cli.py", "--binary", binary, "--profile", source / "profiles/safari-26-ios.json"])
    validate_tree(source)
    if before != input_digest():
        raise SystemExit("build inputs changed while building; refusing build record")
    binaries = {"cfapi": sha256(binary), "challenge": sha256(binary_directory / "challenge")}
    record = {"schema_version": 1, "skill_version": lock["skill_version"], "upstream_revision": lock["revision"], "build_inputs_sha256": before, "rustc": rust, "platform": package_platform, "architecture": package_arch, "cargo_target": target, "build_host_architecture": platform.machine(), "release_debug_assertions": True, "path_remapping": True, "tests": ["upstream-library", "cfapi-unit", "loopback-cli"], "binaries_sha256": binaries, "built_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (source / "skill-build.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Build and local regression tests passed")

if __name__ == "__main__":
    main()
