#!/usr/bin/env python3
"""Write df/prefs/init.txt and d_init.txt from DF's stock defaults plus our four token edits.

  python3 docker/prefs_overrides.py [DF_DIR]          # default: df (relative to the repo root)
  python3 docker/prefs_overrides.py DF_DIR --check     # exit 1 if the files in DF_DIR/prefs differ from the result

The public export ships these edits instead of copies of DF's files (LICENSING.md, "split, don't blend"): every
other line comes from the user's own DF install (data/init/*_default.txt). The private repo still tracks the
resulting files, and this script reproduces them byte for byte.
"""
import os, sys

OVERRIDES = {
    "init.txt": ("init_default.txt", {"FPS_CAP": "10000", "PRINT_MODE": "TEXT"}),
    "d_init.txt": ("d_init_default.txt", {"AUTOSAVE": "NONE", "MULTITHREADING": "NO"}),
}


def render(default_text, edits):
    seen, out = set(), []
    for line in default_text.splitlines(keepends=True):
        s = line.strip()
        if s.startswith("[") and ":" in s:
            key = s[1:s.index(":")]
            if key in edits:
                end = line[len(line.rstrip("\r\n")):]
                line = line[:line.index("[")] + f"[{key}:{edits[key]}]" + end
                seen.add(key)
        out.append(line)
    missing = set(edits) - seen
    if missing:
        sys.exit(f"prefs_overrides: {sorted(missing)} not found in the default file (DF version changed?)")
    return "".join(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    df = args[0] if args else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "df")
    check, bad = "--check" in sys.argv, 0
    os.makedirs(os.path.join(df, "prefs"), exist_ok=True)
    for name, (default, edits) in OVERRIDES.items():
        with open(os.path.join(df, "data", "init", default), newline="") as f:
            text = render(f.read(), edits)
        dst = os.path.join(df, "prefs", name)
        if check:
            with open(dst, newline="") as f:
                ok = f.read() == text
            print(f"{dst}: {'ok' if ok else 'DIFFERS'}")
            bad += not ok
        else:
            with open(dst, "w", newline="") as f:
                f.write(text)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
