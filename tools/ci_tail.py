#!/usr/bin/env python3
"""Dump the tail of the failing step log verbatim."""
import json
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "TIANJING-qwq/nanoapps-senren-banka"

cred = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True).stdout
token = next(l.split("=", 1)[1] for l in cred.splitlines()
             if l.startswith("password="))


def gh(url):
    return urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}",
                      "User-Agent": "ci-log-fetch"})


runs = json.load(urllib.request.urlopen(
    gh(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1")))
run = runs["workflow_runs"][0]
jobs = json.load(urllib.request.urlopen(
    gh(f'https://api.github.com/repos/{REPO}/actions/runs/{run["id"]}/jobs')))
job = jobs["jobs"][0]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = urllib.request.build_opener(NoRedirect)
try:
    opener.open(gh(f'https://api.github.com/repos/{REPO}/actions/jobs/'
                   f'{job["id"]}/logs'))
    sys.exit("no redirect?")
except urllib.error.HTTPError as e:
    url = e.headers["Location"]
log = urllib.request.urlopen(
    urllib.request.Request(url, headers={"User-Agent": "w"})).read().decode(
        "utf-8", "replace")
lines = log.splitlines()
# the Package step block
start = 0
for i, l in enumerate(lines):
    if "Package .nanoapp folder" in l and "##[group]" in l:
        start = i
print("\n".join(lines[max(start, len(lines) - 60):]))
