#!/usr/bin/env python3
"""Download the newest 'vn-nanoapp' artifact from GitHub Actions and unpack
it to a target folder (default: H:\\Apps staging via --out)."""
import io
import json
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = "TIANJING-qwq/nanoapps-senren-banka"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("NanoApps/build/nanoapp_dl")

cred = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True).stdout
token = next(l.split("=", 1)[1] for l in cred.splitlines()
             if l.startswith("password="))


def gh(url):
    return urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}",
                      "Accept": "application/vnd.github+json",
                      "User-Agent": "vn-deploy"})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


runs = json.load(urllib.request.urlopen(
    gh(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=5")))
done = [r for r in runs["workflow_runs"] if r["conclusion"] == "success"]
if not done:
    sys.exit("no successful run")
run = done[0]
print(f'run {run["id"]} sha {run["head_sha"][:7]} {run["display_title"][:50]}')

arts = json.load(urllib.request.urlopen(
    gh(f'https://api.github.com/repos/{REPO}/actions/runs/{run["id"]}/artifacts')))
art = next((a for a in arts["artifacts"] if "nanoapp" in a["name"]), None)
if not art:
    sys.exit(f'no nanoapp artifact: {[a["name"] for a in arts["artifacts"]]}')

req = gh(f'https://api.github.com/repos/{REPO}/actions/artifacts/{art["id"]}/zip')
opener = urllib.request.build_opener(NoRedirect)
try:
    opener.open(req)
    sys.exit("expected a redirect")
except urllib.error.HTTPError as e:
    if e.code not in (301, 302, 307):
        raise
    url = e.headers["Location"]
data = urllib.request.urlopen(
    urllib.request.Request(url, headers={"User-Agent": "vn-deploy"})).read()
print(f'artifact {art["name"]} {len(data) // 1024} KB')

OUT.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BytesIO(data)) as z:
    z.extractall(OUT)
    print("unpacked:", z.namelist()[:6])

for p in OUT.rglob("vn.hbapp"):
    print("hbapp:", p, p.stat().st_size, "B")
