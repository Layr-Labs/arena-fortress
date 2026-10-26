"""Evidence collection: the submission/ diff (bounded, annotated with head line numbers), the file inventory, the
note, declared dependencies, the prior submissions in --context-dir, and score metrics. Everything read here except
the git object ids is untrusted data: it is only ever placed inside delimited blocks of the user message."""
import hashlib, json, os, re, subprocess

# Limits (characters of annotated text unless noted). Recorded in the dossier.
LIMITS = {
    "max_changed_files": 500,        # more -> hold (size_limit)
    "max_file_chars": 60_000,        # a file whose annotated diff is longer is inventoried (name/size/hash + excerpt)
    "excerpt_chars": 3_000,          # head excerpt shown for an inventoried text file
    "max_deleted_lines_shown": 200,  # per file; deletions are summarised beyond this
    "chunk_chars": 300_000,          # one review chunk of the diff (~90k tokens)
    "max_chunks": 4,                 # more -> hold (size_limit)
    "max_note_chars": 40_000,        # longer -> hold (size_limit)
    "max_deps_bytes": 65_536,        # Yukon's own declaration cap
    "context_chars_each": 40_000,    # per prior submission (added lines + note), truncated beyond
    "context_chars_total": 160_000,
    "max_context_submissions": 12,
    "max_blob_bytes": 32 * 1024 * 1024,
}

SUB = "submission/"


class LimitHit(Exception):
    """A size limit was hit: the judgment is a hold, never a pass."""


class InputError(Exception):
    """Unusable inputs (bad sha, unreadable file): the judgment is a hold."""


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_text(s):
    return sha256_bytes(s.encode("utf-8"))


def _git(repo, *args, binary=False, check=True):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
           "HOME": os.environ.get("HOME", "/nonexistent"), "LC_ALL": "C"}
    cmd = ["git", "-C", repo, "-c", "core.quotepath=false", "-c", "core.fsmonitor=false", "-c", "diff.external=",
           "-c", "core.pager=cat", *args]
    p = subprocess.run(cmd, capture_output=True, env=env)
    if check and p.returncode != 0:
        raise InputError(f"git {args[0]} failed ({p.returncode}): {p.stderr.decode('utf-8', 'replace')[:300]}")
    return p.stdout if binary else p.stdout.decode("utf-8", "replace")


def resolve(repo, rev):
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}|[A-Za-z0-9._/@^~-]{1,200}", rev or ""):
        raise InputError(f"bad revision {rev!r}")
    return _git(repo, "rev-parse", "--verify", "--end-of-options", rev + "^{commit}").strip()


def _raw_changes(repo, base, head):
    out = _git(repo, "diff", "--raw", "-z", "--no-abbrev", "-M", "--no-color", base, head, "--", SUB, binary=True)
    parts = out.split(b"\0")
    i, changes = 0, []
    while i < len(parts) and parts[i]:
        meta = parts[i].decode("utf-8", "replace").lstrip(":").split()
        status = meta[4]
        old_sha, new_sha = meta[2], meta[3]
        if status[0] in "RC":
            old, new = parts[i + 1].decode("utf-8", "replace"), parts[i + 2].decode("utf-8", "replace")
            i += 3
        else:
            old = new = parts[i + 1].decode("utf-8", "replace")
            i += 2
        changes.append({"status": status[0], "similarity": status[1:] or None, "old_path": old, "path": new,
                        "old_blob": old_sha, "new_blob": new_sha})
    return changes


def _blob(repo, sha):
    if not sha or set(sha) == {"0"}:
        return None
    size = int(_git(repo, "cat-file", "-s", sha).strip())
    if size > LIMITS["max_blob_bytes"]:
        raise LimitHit(f"a file in submission/ is {size} bytes, over the {LIMITS['max_blob_bytes']}-byte judge limit")
    return _git(repo, "cat-file", "blob", sha, binary=True)


def is_binary(b):
    if b is None:
        return False
    if b"\0" in b[:8192]:
        return True
    try:
        b.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def annotate_patch(patch, max_deleted=None):
    """Unified diff of one file -> (annotated text, added [(lineno, text)]). Added and context lines carry their
    line number in the new file, so reviewers can cite path:line."""
    out, added, deleted_shown, deleted_more = [], [], 0, 0
    new_no = None
    in_hunk = False
    for line in patch.split("\n"):
        m = HUNK.match(line)
        if m:
            new_no = int(m.group(3))
            in_hunk = True
            out.append(f"      @@ new line {new_no} @@")
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            out.append(f"{new_no:>6} + {line[1:]}")
            added.append((new_no, line[1:]))
            new_no += 1
        elif line.startswith("-"):
            if max_deleted is None or deleted_shown < max_deleted:
                out.append(f"       - {line[1:]}")
                deleted_shown += 1
            else:
                deleted_more += 1
        elif line.startswith(" "):
            out.append(f"{new_no:>6}   {line[1:]}")
            new_no += 1
        elif line.startswith("\\"):
            continue
    if deleted_more:
        out.append(f"       ... {deleted_more} more deleted lines not shown")
    return "\n".join(out), added


def split_patch_files(patch):
    """A multi-file unified diff (context submissions) -> [(path, file patch)]."""
    files, cur, path = [], [], None
    for line in patch.split("\n"):
        if line.startswith("diff --git "):
            if cur:
                files.append((path, "\n".join(cur)))
            cur, path = [line], None
            m = re.match(r"diff --git a/(.*?) b/(.*)$", line)
            if m:
                path = m.group(2)
            continue
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            p = line[4:].strip()
            path = p[2:] if p.startswith("b/") else p
        cur.append(line)
    if cur:
        files.append((path, "\n".join(cur)))
    return [(p or "?", t) for p, t in files]


def collect_submission(repo, base, head):
    base_sha, head_sha = resolve(repo, base), resolve(repo, head)
    changes = _raw_changes(repo, base_sha, head_sha)
    if len(changes) > LIMITS["max_changed_files"]:
        raise LimitHit(f"{len(changes)} changed files in submission/, over the {LIMITS['max_changed_files']} limit")
    files, segments, scan_lines = [], [], []
    for ch in changes:
        new = _blob(repo, ch["new_blob"])
        old = _blob(repo, ch["old_blob"]) if ch["status"] in "MRCT" else None
        binary = is_binary(new) or is_binary(old)
        entry = {"path": ch["path"], "status": ch["status"], "old_path": ch["old_path"] if ch["status"] in "RC" else None,
                 "size": len(new) if new is not None else 0,
                 "sha256": sha256_bytes(new) if new is not None else None, "binary": binary,
                 "added": 0, "deleted": 0, "shown": "diff"}
        if binary:
            entry["shown"] = "inventory"
            files.append(entry)
            continue
        specs = [":(literal)" + ch["path"]]
        if entry["old_path"]:
            specs.insert(0, ":(literal)" + ch["old_path"])
        patch = _git(repo, "diff", "--no-color", "--no-ext-diff", "--no-textconv", "-M", "-U3", base_sha, head_sha,
                     "--", *specs)
        text, added = annotate_patch(patch, LIMITS["max_deleted_lines_shown"])
        entry["added"] = len(added)
        entry["deleted"] = sum(1 for l in patch.split("\n") if l.startswith("-") and not l.startswith("---"))
        if ch["status"] != "D":
            scan_lines += [(ch["path"], n, t) for n, t in added]
        header = (f"### FILE {ch['path']}  (status {ch['status']}"
                  + (f", renamed from {entry['old_path']}" if entry["old_path"] else "")
                  + f", +{entry['added']} -{entry['deleted']}, head size {entry['size']} B, sha256 {entry['sha256']})")
        if len(text) > LIMITS["max_file_chars"]:
            entry["shown"] = "inventory+excerpt"
            excerpt = new.decode("utf-8", "replace")[:LIMITS["excerpt_chars"]] if new else ""
            numbered = "\n".join(f"{i + 1:>6}   {l}" for i, l in enumerate(excerpt.split("\n")))
            text = (f"{header}\n      [large file: diff not shown ({len(text)} chars annotated); first "
                    f"{LIMITS['excerpt_chars']} chars of the head version follow]\n{numbered}")
        else:
            text = f"{header}\n{text}"
        entry["added_lines"] = added      # dropped before the dossier is written
        segments.append((ch["path"], text))
        files.append(entry)
    chunks, chunk_files, cur, cur_files = [], [], "", []
    for path, seg in segments:
        if cur and len(cur) + len(seg) + 2 > LIMITS["chunk_chars"]:
            chunks.append(cur)
            chunk_files.append(cur_files)
            cur, cur_files = "", []
        cur += seg + "\n\n"
        cur_files.append(path)
    if cur:
        chunks.append(cur)
        chunk_files.append(cur_files)
    if len(chunks) > LIMITS["max_chunks"]:
        raise LimitHit(f"the submission/ diff needs {len(chunks)} review chunks, over the {LIMITS['max_chunks']} limit")
    inventory = [f"{f['path']}  status={f['status']} size={f['size']} sha256={f['sha256']} "
                 f"{'binary' if f['binary'] else 'text'} +{f['added']} -{f['deleted']} shown={f['shown']}"
                 for f in files]
    return {"base": base_sha, "head": head_sha, "files": files, "chunks": chunks or ["(no changes in submission/)"],
            "chunk_files": chunk_files or [[]], "segments": dict(segments),
            "inventory": "\n".join(inventory) or "(no changed files)", "scan_lines": scan_lines,
            "diff_sha256": sha256_text("".join(t for _, t in segments))}


# ----------------------------------------------------------------------------------------------- other inputs

def read_text(path, limit=None, what="file"):
    try:
        with open(path, "rb") as f:
            b = f.read()
    except OSError as e:
        raise InputError(f"cannot read {what}: {e.strerror}")
    s = b.decode("utf-8", "replace")
    if limit is not None and len(s) > limit:
        raise LimitHit(f"the {what} is {len(s)} chars, over the {limit} limit")
    return s, sha256_bytes(b)


def load_dependencies(path):
    s, h = read_text(path, LIMITS["max_deps_bytes"], "dependencies file")
    try:
        d = json.loads(s)
    except ValueError:
        raise InputError("dependencies file is not JSON")
    if isinstance(d, dict):
        d = d.get("dependencies", [])
    if not isinstance(d, list):
        raise InputError("dependencies must be a JSON array (Yukon's --dependencies-file format)")
    deps = []
    for e in d:
        if isinstance(e, str):
            e = {"submissionId": e}
        if not isinstance(e, dict) or not isinstance(e.get("submissionId") or e.get("id"), str):
            raise InputError("each dependency needs a submissionId")
        deps.append({"submissionId": (e.get("submissionId") or e.get("id")).strip().lower(),
                     "rationale": str(e.get("rationale", ""))[:4000], "evidence": str(e.get("evidence", ""))[:8000]})
    return deps, h


def _norm(line):
    s = " ".join(line.strip().split())
    return s if len(s) >= 16 and re.search(r"[A-Za-z]", s) else None


def patch_added(patch):
    """A multi-file diff of a prior submission -> (annotated added-line text, set of normalised added lines). The
    overlap table and the workflow's overlap scan (runner/ci/bin/prior.py) both use this."""
    body, added_norm = [], set()
    for path, fp in split_patch_files(patch):
        if path.startswith("/dev/null"):
            continue
        _, added = annotate_patch(fp)
        if not added:
            continue
        body.append(f"### {path} (lines this submission added)")
        body += [f"{ln:>6} + {t}" for ln, t in added]
        added_norm |= {x for x in (_norm(t) for _, t in added) if x}
    return body, added_norm


def _same_person(a, b):
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def load_context(ctx_dir, declared_ids, base_producers, submitter=None):
    """Prior public submissions: <ctx_dir>/<subdir>/{meta.json, diff.patch[, note.md]}. `own`: the context
    submission is by the same submitter (reuse of one's own earlier work is not undeclared copying, RULES §8)."""
    subs = []
    if not ctx_dir:
        return subs
    if not os.path.isdir(ctx_dir):
        raise InputError("--context-dir is not a directory")
    names = sorted(n for n in os.listdir(ctx_dir) if os.path.isdir(os.path.join(ctx_dir, n)))
    if len(names) > LIMITS["max_context_submissions"]:
        names = names[:LIMITS["max_context_submissions"]]   # the workflow orders/limits; recorded as truncated
    each = min(LIMITS["context_chars_each"], LIMITS["context_chars_total"] // max(1, len(names)))
    for n in names:
        d = os.path.join(ctx_dir, n)
        meta = {}
        if os.path.exists(os.path.join(d, "meta.json")):
            try:
                meta = json.loads(read_text(os.path.join(d, "meta.json"), 100_000, f"context {n} meta")[0])
            except ValueError:
                raise InputError(f"context {n}: meta.json is not JSON")
            if not isinstance(meta, dict):
                raise InputError(f"context {n}: meta.json is not an object")
        sid = str(meta.get("submission_id") or meta.get("id") or n).strip().lower()
        patch, ph = ("", None)
        if os.path.exists(os.path.join(d, "diff.patch")):
            patch, ph = read_text(os.path.join(d, "diff.patch"), None, f"context {n} diff")
        note = meta.get("note") or ""
        if os.path.exists(os.path.join(d, "note.md")):
            note, _ = read_text(os.path.join(d, "note.md"), None, f"context {n} note")
        body, added_norm = patch_added(patch)
        text = "\n".join(body)
        note = note[:8000]
        truncated = len(text) + len(note) > each
        if truncated:
            text = text[:max(0, each - len(note))] + "\n... [truncated by the judge]"
        subs.append({"id": sid, "dir": n, "submitter": str(meta.get("submitter", ""))[:100],
                     "coauthors": [str(c)[:100] for c in meta.get("coauthors", [])][:20]
                     if isinstance(meta.get("coauthors"), list) else [],
                     "status": str(meta.get("status", ""))[:40], "title": str(meta.get("title", ""))[:200],
                     "why": str(meta.get("why", ""))[:40],
                     "own": _same_person(str(meta.get("submitter", "")), submitter or ""),
                     "produced_base": bool(meta.get("produced_base")) or sid in base_producers,
                     "declared": sid in declared_ids, "note": note, "text": text, "truncated": truncated,
                     "diff_sha256": ph, "added_norm": added_norm})
    return subs


def overlap(sub_scan_lines, contexts):
    head = {}
    for path, ln, t in sub_scan_lines:
        k = _norm(t)
        if k and k not in head:
            head[k] = f"{path}:{ln}"
    stats = []
    for c in contexts:
        shared = [k for k in head if k in c["added_norm"]]
        stats.append({"context_id": c["id"], "declared": c["declared"], "produced_base": c["produced_base"],
                      "own": c.get("own", False),
                      "shared_lines": len(shared), "head_added_lines": len(head),
                      "fraction": round(len(shared) / len(head), 3) if head else 0.0,
                      "samples": [{"at": head[k], "line": k[:160]} for k in shared[:5]]})
    return stats


def load_context_status(ctx_dir):
    """What the workflow recorded about building the context (prior.py's _scan.json and _errors.json): whether the
    overlap scan over all the row's submissions ran, what it skipped, and any degraded inputs. Recorded in the
    dossier; never shown to a model."""
    out = {}
    for name in ("_scan.json", "_errors.json"):
        p = os.path.join(ctx_dir or "", name)
        if ctx_dir and os.path.isfile(p):
            try:
                out[name[1:-5]] = json.loads(read_text(p, 200_000, f"context {name}")[0])
            except ValueError:
                out[name[1:-5]] = {"error": f"{name} is not JSON"}
    return out


def load_score(path):
    if not path:
        return None, None
    s, h = read_text(path, 1_000_000, "score json")
    try:
        d = json.loads(s)
    except ValueError:
        return {"unparsed": True}, h
    keep = {}
    if isinstance(d, dict):
        if isinstance(d.get("score"), (int, float, str)):
            keep["score"] = d["score"]
        m = d.get("metrics") if isinstance(d.get("metrics"), dict) else {}
        for k, v in list(m.items())[:40]:
            if isinstance(v, (int, float, str, bool)) or v is None:
                keep[str(k)[:60]] = v if not isinstance(v, str) else v[:100]
    return keep, h
