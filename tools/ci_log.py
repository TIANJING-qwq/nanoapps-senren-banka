#!/usr/bin/env python3
"""Fetch the failing CI job's log using the stored git credential token."""
import json
import subprocess
import sys
import urllib.request

REPO = "TIANJING-qwq/nanoapps-senren-banka"

cred = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True).stdout
token = ""
for ln in cred.splitlines():
    if ln.startswith("password="):
        token = ln.split("=", 1)[1]
if not token:
    sys.exit("no token in git credential store")

req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1",
    headers={"Authorization": f"Bearer {token}",
             "Accept": "application/vnd.github+json",
             "User-Agent": "ci-log-fetch"})
runs = json.load(urllib.request.urlopen(req))
run = runs["workflow_runs"][0]
print(f'run {run["id"]} ({run["head_sha"][:7]}) {run["status"]}')
req = urllib.request.Request(
    f'https://api.github.com/repos/{REPO}/actions/runs/{run["id"]}/jobs',
    headers={"Authorization": f"Bearer {token}",
             "Accept": "application/vnd.github+json",
             "User-Agent": "ci-log-fetch"})
jobs = json.load(urllib.request.urlopen(req))
job = jobs["jobs"][0]
print("steps:", [(s["name"], s["conclusion"]) for s in job["steps"]])
if job["conclusion"] != "success":
    req = urllib.request.Request(
        f'https://api.github.com/repos/{REPO}/actions/jobs/{job["id"]}/logs',
        headers={"Authorization": f"Bearer {token}",
                 "User-Agent": "ci-log-fetch"})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(req)
        log_url = None
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 307):
            raise
        log_url = e.headers["Location"]
    log = urllib.request.urlopen(
        urllib.request.Request(log_url,
                               headers={"User-Agent": "ci-log-fetch"})
    ).read().decode("utf-8", "replace")
    lines = log.splitlines()
    tail = [l for l in lines if any(k in l for k in (
        "error", "Error", "FAILED", "Traceback", "exit code", "✗"))][-25:]
    print("--- relevant log tail ---")
    print("\n".join(tail))
