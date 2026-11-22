import io
import json
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = "TIANJING-qwq/nanoapps-senren-banka"
RUN_ID = int(sys.argv[1])
OUT = Path(sys.argv[2])

cred = subprocess.run(["git", "credential", "fill"],
                      input="protocol=https\nhost=github.com\n\n",
                      capture_output=True, text=True).stdout
tok = next(l.split("=", 1)[1] for l in cred.splitlines()
           if l.startswith("password="))


def gh(u):
    return urllib.request.Request(
        u, headers={"Authorization": "Bearer " + tok, "User-Agent": "vn"})


class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a):
        return None


arts = json.load(urllib.request.urlopen(
    gh(f"https://api.github.com/repos/{REPO}/actions/runs/{RUN_ID}/artifacts")))
art = next(a for a in arts["artifacts"] if "nanoapp" in a["name"])
try:
    urllib.request.build_opener(NR).open(
        gh(f'https://api.github.com/repos/{REPO}/actions/artifacts/{art["id"]}/zip'))
    sys.exit("expected redirect")
except urllib.error.HTTPError as e:
    url = e.headers["Location"]
data = urllib.request.urlopen(
    urllib.request.Request(url, headers={"User-Agent": "vn"})).read()
OUT.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BytesIO(data)) as z:
    z.extractall(OUT)
    for n in z.namelist():
        if n.endswith(".zip"):
            with zipfile.ZipFile(OUT / n) as z2:
                z2.extractall(OUT)
print("ok:", [str(p) for p in OUT.rglob("*.hbapp")])
