#!/usr/bin/env python3
"""Run start's setup_fontawesome + setup_lvgl so build_apps.py can run
on this Windows box (no ARM toolchain needed for packaging only)."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_loader(
    "startmod", loader=None,
    origin=str(Path("NanoApps/start").resolve()))
src = Path("NanoApps/start").read_text(encoding="utf-8")
# strip the shebang/argparse main guard by exec'ing the module body up to
# the main() call; simplest: exec whole file with __name__ != "__main__"
mod = type(sys)("startmod")
mod.__name__ = "startmod"
mod.__file__ = str(Path("NanoApps/start").resolve())
exec(compile(src, mod.__file__, "exec"), mod.__dict__)
mod.setup_fontawesome()
print("FA ok:", (mod.FA_DIR / "metadata" / "icons.json").is_file())
