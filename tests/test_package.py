#!/usr/bin/env python3
"""归档完整性和路径边界回归；不执行归档内程序。"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_package import verify

ROOT = "cloudflare-bypass-cfsolve"
PREFIX = ROOT + "/"
FILES = {name: b"VALIDATOR_TEST_ONLY" for name in (
    "SKILL.md", "bin/cfapi", "bin/challenge", "scripts/run.py",
    "profiles/safari-26-ios.json", "licenses/cfsolve-LICENSE",
)}


def fixture(path, case):
    manifest = {"version": "validator-test", "build": {"platform": "linux", "architecture": "x86_64"},
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in FILES.items()}}
    contents = {PREFIX + name: data for name, data in FILES.items()}
    contents[PREFIX + "manifest.json"] = json.dumps(manifest).encode()
    if case == "tamper":
        contents[PREFIX + "bin/cfapi"] = b"TAMPERED"
    if case == "outside-root":
        # 相同长度的其他根目录不能冒充 manifest 中已有的文件。
        contents["x" * len(ROOT) + "/SKILL.md"] = FILES["SKILL.md"]
    if case == "traversal":
        contents[PREFIX + "../outside"] = b"bad"
    if case == "path-alias":
        contents[PREFIX + "./SKILL.md"] = FILES["SKILL.md"]
    if case == "extra-file":
        contents[PREFIX + "unlisted"] = b"bad"
    with tarfile.open(path, "w:gz") as archive:
        directory = tarfile.TarInfo(ROOT)
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, data in contents.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if case == "symlink":
            member = tarfile.TarInfo(PREFIX + "link")
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/outside"
            archive.addfile(member)


class PackageTests(unittest.TestCase):
    def test_valid_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.tar.gz"
            fixture(path, "valid")
            with contextlib.redirect_stdout(io.StringIO()):
                verify(path)

    def test_rejects_tampering_and_unsafe_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in ("tamper", "outside-root", "traversal", "path-alias", "extra-file", "symlink"):
                with self.subTest(case=case):
                    path = Path(directory) / (case + ".tar.gz")
                    fixture(path, case)
                    with self.assertRaises(ValueError):
                        verify(path)


if __name__ == "__main__":
    unittest.main()
