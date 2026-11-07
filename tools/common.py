"""构建工具共享逻辑，仅使用 Python 标准库。"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def load_lock():
    return json.loads((ROOT / "upstream.lock.json").read_text())

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def run(argv, cwd=None, env=None):
    subprocess.run([str(x) for x in argv], cwd=cwd, env=env, check=True)

def input_digest():
    paths = [ROOT / "upstream.lock.json"]
    for folder in ("overlay", "patches"):
        paths += [p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(str(path.relative_to(ROOT)).encode() + b"\0" + bytes.fromhex(sha256(path)))
    return h.hexdigest()

def validate_tree(source):
    source = Path(source).resolve()
    lock = load_lock()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if head != lock["revision"] or sha256(source / "Cargo.lock") != lock["cargo_lock_sha256"]:
        raise ValueError("upstream revision/Cargo.lock differs from lock")
    diff = subprocess.check_output(["git", "diff", "--no-ext-diff", "--no-color", "HEAD", "--"], cwd=source)
    if diff != (ROOT / "patches/integration.patch").read_bytes():
        raise ValueError("tracked source differs from reviewed integration patch")
    for path in (ROOT / "overlay").rglob("*"):
        if path.is_file() and path.read_bytes() != (source / path.relative_to(ROOT / "overlay")).read_bytes():
            raise ValueError("overlay source differs")
    for relative, expected in lock["profile_sha256"].items():
        if sha256(source / relative) != expected:
            raise ValueError("upstream profile differs from lock")
        runtime = ROOT / "skill/cloudflare-bypass-cfsolve" / relative
        if sha256(runtime) != expected:
            raise ValueError("runtime profile differs from lock")
    runtime_root = ROOT / "skill/cloudflare-bypass-cfsolve"
    actual_profiles = {str(p.relative_to(runtime_root)) for p in (runtime_root / "profiles").rglob("*") if p.is_file()}
    if actual_profiles != set(lock["profile_sha256"]):
        raise ValueError("runtime profile file set differs from lock")
    return source
