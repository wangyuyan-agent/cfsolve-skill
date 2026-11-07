#!/usr/bin/env python3
"""在新目录检出固定上游，检查后应用最小补丁；不覆盖已有目录。"""
import argparse
import shutil
from pathlib import Path
from common import ROOT, load_lock, run, sha256, validate_tree

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--local-upstream", type=Path)
    args = parser.parse_args()
    lock = load_lock()
    if args.dest.exists():
        raise SystemExit("destination already exists; choose a new directory")
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    if args.local_upstream:
        run(["git", "clone", "--no-checkout", "--no-hardlinks", args.local_upstream.resolve(), args.dest])
    else:
        run(["git", "init", "-q", args.dest])
        run(["git", "remote", "add", "origin", lock["repository"]], args.dest)
        run(["git", "fetch", "--depth=1", "origin", lock["revision"]], args.dest)
    run(["git", "checkout", "--detach", lock["revision"]], args.dest)
    if sha256(args.dest / "Cargo.lock") != lock["cargo_lock_sha256"]:
        raise SystemExit("Cargo.lock hash mismatch")
    patch = ROOT / "patches/integration.patch"
    run(["git", "apply", "--check", patch], args.dest)
    run(["git", "apply", patch], args.dest)
    for source in (ROOT / "overlay").rglob("*"):
        if source.is_file():
            target = args.dest / source.relative_to(ROOT / "overlay")
            if target.exists():
                raise SystemExit("overlay collides with upstream: " + str(source.relative_to(ROOT)))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    validate_tree(args.dest)
    print("Prepared pinned source:", args.dest)

if __name__ == "__main__":
    main()
