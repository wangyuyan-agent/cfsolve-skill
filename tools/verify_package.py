#!/usr/bin/env python3
"""校验归档路径、文件列表、SHA-256 和关键产物，不执行包内程序。"""
import argparse
import hashlib
import json
from pathlib import PurePosixPath
import tarfile

def verify(path):
    with tarfile.open(path, "r:gz") as tar:
        members = tar.getmembers()
        names = set()
        prefix = "cloudflare-bypass-cfsolve/"
        for member in members:
            name = PurePosixPath(member.name)
            canonical = name.as_posix()
            supplied = member.name.rstrip("/") if member.isdir() else member.name
            in_root = (canonical == prefix[:-1] and member.isdir()) or canonical.startswith(prefix)
            if not in_root or supplied != canonical or "\\" in member.name or name.is_absolute() or ".." in name.parts or canonical in names or not (member.isfile() or member.isdir()):
                raise ValueError("unsafe or duplicate archive entry")
            names.add(canonical)
        manifest = json.load(tar.extractfile(prefix + "manifest.json"))
        actual_files = {m.name[len(prefix):] for m in members if m.isfile() and m.name != prefix + "manifest.json"}
        if actual_files != set(manifest["files"]):
            raise ValueError("manifest file set mismatch")
        for name, expected in manifest["files"].items():
            actual = hashlib.sha256(tar.extractfile(prefix + name).read()).hexdigest()
            if actual != expected:
                raise ValueError("file checksum mismatch: " + name)
        for required in ["SKILL.md", "bin/cfapi", "bin/challenge", "scripts/run.py", "profiles/safari-26-ios.json", "licenses/cfsolve-LICENSE"]:
            if required not in actual_files:
                raise ValueError("missing required artifact")
        print(json.dumps({"verified": True, "files": len(actual_files), "version": manifest["version"], "platform": manifest["build"]["platform"], "architecture": manifest["build"]["architecture"]}))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    verify(parser.parse_args().archive)
