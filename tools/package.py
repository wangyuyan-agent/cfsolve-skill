#!/usr/bin/env python3
"""从已验证构建生成平台 skill 包和可维护源码包。"""
import argparse
import gzip
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from common import ROOT, input_digest, load_lock, sha256, validate_tree

RUNTIME_FILES = (
    "SKILL.md", "scripts/run.py", "scripts/mint_recaptcha_v3.cjs",
    "references/request-schema.md", "references/recaptcha-v3.md",
    "references/troubleshooting.md", "references/maintenance.md",
)
SOURCE_FILES = (
    "LICENSE", "README.md", "README.zh-CN.md", "SECURITY.md", "DEPENDENCIES.md", "upstream.lock.json", ".gitignore",
    "overlay/src/http/api.rs", "overlay/examples/cfapi.rs", "patches/integration.patch",
    "tools/common.py", "tools/prepare.py", "tools/build.py", "tools/package.py",
    "tools/verify_package.py", "tools/check_upstream.py",
    "tools/check_public.py", "tools/smoke_package.py",
    "tests/test_cli.py", "tests/test_recaptcha.cjs", "tests/test_package.py",
    "tests/browser/package.json", "tests/browser/package-lock.json", "tests/browser/recaptcha.cjs",
    ".github/workflows/build.yml", ".github/workflows/upstream-watch.yml",
)

def copy_files(source, target, relative_paths):
    for relative in relative_paths:
        path = source / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or linked package input: " + relative)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

def archive(directory, destination):
    with destination.open("xb") as output, gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in [directory, *sorted(directory.rglob("*"))]:
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    raise ValueError("package contains a link or special file")
                info = tar.gettarinfo(str(path), arcname=str(path.relative_to(directory.parent)))
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                info.mode = 0o755 if path.is_dir() or (path.is_file() and ("bin" in path.relative_to(directory).parts or path.suffix in (".py", ".cjs", ".sh"))) else 0o644
                if path.is_file():
                    with path.open("rb") as stream: tar.addfile(info, stream)
                else:
                    tar.addfile(info)

def license_files(source, target):
    destination = target / "licenses"
    destination.mkdir()
    shutil.copy2(source / "LICENSE", destination / "cfsolve-LICENSE")
    metadata = json.loads((source / "dependencies.json").read_text())
    entries = []
    for package in metadata["packages"]:
        root = Path(package["manifest_path"]).parent
        name = f"{package['name']}-{package['version']}"
        copies = []
        candidates = [p for p in root.iterdir() if p.is_file() and p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "COPYRIGHT", "NOTICE"))]
        if package.get("license_file"):
            candidates.append(root / package["license_file"])
        for path in sorted(set(candidates)):
            if path.is_file() and not path.is_symlink():
                to = destination / name / path.name
                to.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, to)
                copies.append(str(to.relative_to(target)))
        entries.append({"name": package["name"], "version": package["version"], "license": package.get("license"), "repository": package.get("repository"), "license_files": copies})
    # BoringSSL 是嵌套的 C/C++ 依赖，不是单独 Cargo package。
    for path in (source / "vendor").rglob("*"):
        if path.is_file() and not path.is_symlink() and path.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
            to = destination / "vendor" / path.relative_to(source / "vendor")
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, to)
    (destination / "DEPENDENCIES.json").write_text(json.dumps(entries, indent=2) + "\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = validate_tree(args.source)
    lock = load_lock()
    record = json.loads((source / "skill-build.json").read_text())
    if record["build_inputs_sha256"] != input_digest() or record["upstream_revision"] != lock["revision"]:
        raise SystemExit("build record does not match current source inputs")
    binary_directory = source / "target" / (record.get("cargo_target") or "") / "release"
    binaries = {"cfapi": binary_directory / "examples/cfapi", "challenge": binary_directory / "challenge"}
    for name, path in binaries.items():
        if sha256(path) != record["binaries_sha256"][name]:
            raise SystemExit("binary does not match verified build record")
    args.out.mkdir(parents=True, exist_ok=True)
    architecture = {"x86_64": "x64", "AMD64": "x64", "aarch64": "arm64"}.get(record["architecture"], record["architecture"])
    platform = f"{record['platform']}-{architecture}"
    with tempfile.TemporaryDirectory(prefix="cfsolve-package-") as temporary:
        root = Path(temporary)
        skill = root / "cloudflare-bypass-cfsolve"
        runtime_files = [*RUNTIME_FILES, *lock["profile_sha256"]]
        copy_files(ROOT / "skill/cloudflare-bypass-cfsolve", skill, runtime_files)
        (skill / "bin").mkdir()
        for name, path in binaries.items(): shutil.copy2(path, skill / "bin" / name)
        license_files(source, skill)
        shutil.copy2(ROOT / "upstream.lock.json", skill / "upstream.lock.json")
        manifest = {"schema_version": 1, "version": lock["skill_version"], "build": record, "files": {str(p.relative_to(skill)): sha256(p) for p in sorted(skill.rglob("*")) if p.is_file()}}
        (skill / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        runtime = args.out / f"cloudflare-bypass-cfsolve-v{lock['skill_version']}-{platform}.tar.gz"
        archive(skill, runtime)
        kit = root / "cfsolve-skill-source"
        kit.mkdir()
        copy_files(ROOT, kit, SOURCE_FILES)
        copy_files(ROOT / "skill/cloudflare-bypass-cfsolve", kit / "skill/cloudflare-bypass-cfsolve", runtime_files)
        source_archive = args.out / f"cfsolve-skill-v{lock['skill_version']}-source.tar.gz"
        archive(kit, source_archive)
    for path in (runtime, source_archive):
        print(f"{sha256(path)}  {path.name}")
        (path.with_name(path.name + ".sha256")).write_text(f"{sha256(path)}  {path.name}\n")

if __name__ == "__main__":
    main()
