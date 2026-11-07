#!/usr/bin/env python3
"""只检测上游变更并输出候选信息，不修改固定版本、不提交或发布。"""
import argparse
import json
import os
from pathlib import Path
import urllib.request
from common import load_lock

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lock = load_lock()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "cfsolve-skill-upstream-check"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    request = urllib.request.Request("https://api.github.com/repos/chris124567/cfsolve/commits/master", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        commit = json.load(response)
    result = {"changed": commit["sha"] != lock["revision"], "pinned_revision": lock["revision"], "candidate_revision": commit["sha"], "commit_url": commit["html_url"], "committed_at": commit["commit"]["committer"]["date"], "next_step": "Review upstream diff, update lock/profile on a branch, and pass the build workflow before adopting."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    message = f"Upstream changed: {result['changed']}\nPinned: {lock['revision']}\nCandidate: {commit['sha']}\n"
    print(message)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream: stream.write(message)

if __name__ == "__main__":
    main()
