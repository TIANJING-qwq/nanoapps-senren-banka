#!/usr/bin/env python3
"""Recover Yuzusoft hashed filenames by dictionary attack on the XP3
'adlr' values (adler32 of the original storage name)."""
import string
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import unpack_xp3 as ux


def candidates():
    """Yield candidate storage names for a Yuzusoft game."""
    # generic stems
    stems = ["title", "rogo", "logo", "wtitle", "titlebg", "title_bg",
             "title_1", "title1", "titlea", "title_a", "op", "ed",
             "load", "save", "config", "system", "menu", "back",
             "black", "white", "fade", "frame", "window", "default"]
    # numbered series seen in Yuzusoft games
    for pat, kind in (("bg%02d", "n"), ("bg%03d", "n"), ("ev%02d%s", "s"),
                      ("ev%03d%s", "s"), ("cg%02d%s", "s"), ("bg_%02d", "n"),
                      ("ev_%02d%s", "s"), ("ev%02d_%s", "s"), ("ev%02d%s%s", "ss")):
        if kind == "n":
            for i in range(0, 120):
                yield pat % i
        elif kind == "s":
            for i in range(1, 100):
                for a in string.ascii_lowercase:
                    yield pat % (i, a)
        else:                                            # ss: letter + suffix
            for i in range(1, 100):
                for a in string.ascii_lowercase:
                    for b in ("", "_", "b", "c"):
                        yield pat % (i, a, b)
    for s in stems:
        yield s
        yield s + "_1"
        for suf in ("a", "b", "_a", "_b"):
            yield s + suf


def main(archive):
    f = open(archive, "rb")
    table = ux.read_index(f)
    entries = ux.parse_table(table)
    targets = {}
    for name, fsize, segs, adler in entries:
        if adler:
            targets.setdefault(adler, []).append(name)
    print(f"{len(targets)} distinct adler hashes to attack")

    # try variants: bare, .png, folder prefixes, case
    suffixes = ["", ".png", ".PNG"]
    folders = ["", "bgimage/", "bgimage720/", "bg/", "ev/", "image/"]
    hits = 0
    seen = set()
    for stem in candidates():
        for folder in folders:
            for suf in suffixes:
                for form in (stem, stem.upper()):
                    cand = folder + form + suf
                    h = zlib.adler32(cand.encode("utf-8")) & 0xFFFFFFFF
                    if h in targets and cand not in seen:
                        seen.add(cand)
                        for orig in targets[h]:
                            print(f"  {orig} -> {cand}")
                        hits += 1
    print(f"matched {hits} candidates")


if __name__ == "__main__":
    main(sys.argv[1])
