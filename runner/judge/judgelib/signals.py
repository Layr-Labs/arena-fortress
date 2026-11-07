"""Deterministic pre-scan of the submission's added lines and its note. Signals are hints with ids that the
fair-play reviewer must disposition one by one; `high` signals also set a verdict floor: a judgment carrying an
uncleared high signal can't pass, whatever the models say (it holds for an organiser unless a fatal finding is
confirmed). The scan is a cheap tripwire, not the review: it misses things and flags benign code."""
import ipaddress, os, re, unicodedata

CODE_EXT = {".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash", ".zsh", ".go", ".rs", ".rb",
            ".lua", ".java", ".kt", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".ps1", ".pl", ".php", ".r", ".jl",
            ".swift", ".scala", ".ex", ".exs", ".hs", ".ml", ".zig", ".nim", ".dart", ".mk", ".cmake"}
DATA_EXT = {".md", ".txt", ".rst", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".csv", ".tsv", ".ini", ".cfg",
            ".lock", ".sum", ".mod", ".html", ".xml", ".svg"}
DEP_FILES = re.compile(r"(^|/)(requirements[^/]*\.txt|constraints[^/]*\.txt|package(-lock)?\.json|pnpm-lock\.yaml|"
                       r"yarn\.lock|poetry\.lock|uv\.lock|Pipfile(\.lock)?|pyproject\.toml|go\.(mod|sum)|"
                       r"Cargo\.(toml|lock)|Gemfile(\.lock)?|\.dockerignore)$")
ALLOWED_HOSTS = {"game", "gateway", "localhost", "127.0.0.1", "0.0.0.0", "::1"}


def file_kind(path):
    base = os.path.basename(path)
    if base == "Dockerfile" or base.startswith("Dockerfile.") or base.endswith(".dockerfile"):
        return "dockerfile"
    if DEP_FILES.search(path):
        return "deps"
    ext = os.path.splitext(base)[1].lower()
    if ext in DATA_EXT:
        return "data"
    return "code"   # unknown extensions and extensionless scripts count as code


# (kind, level, regex, applies-to kinds)
RULES = [
    ("docker_socket", "high", r"docker\.sock|/var/run/docker|\bDOCKER_HOST\b|containerd\.sock", {"code", "dockerfile", "data", "deps"}),
    ("proc_environ", "high", r"/proc/(?:\d+|self|1)/(?:environ|root|mem)\b", {"code", "dockerfile", "data"}),
    ("raw_socket", "medium", r"\bsocket\s*\.\s*(?:socket|create_connection|getaddrinfo)\b|\bimport\s+socket\b|"
     r"\bfrom\s+socket\s+import\b|\bnet\.(?:Dial|Listen|connect|createConnection)\b|/dev/(?:tcp|udp)/|"
     r"\b(?:nc|ncat|netcat|socat|telnet)\s+-|\bnew\s+WebSocket\b|\bdgram\b|\bAF_PACKET\b|\bSOCK_RAW\b", {"code"}),
    ("dns", "medium", r"\bgethostbyname\b|\bgetaddrinfo\b|\bdns\.resolver\b|\bdnspython\b|resolv\.conf|/etc/hosts\b|"
     r"\bnslookup\b|\bres_query\b|\bdig\s+@|\bdig\s+\+short\b", {"code", "dockerfile"}),
    ("shell_fetch", "medium", r"\b(?:curl|wget|aria2c)\b", {"code"}),
    ("model_bypass", "medium", r"api\.openai\.com|openrouter\.ai|api\.together\.(?:xyz|ai)|api\.anthropic\.com|"
     r"bedrock-runtime|generativelanguage\.googleapis|api\.groq\.com|api\.mistral\.ai|api\.deepseek\.com|"
     r"api\.fireworks\.ai|z\.ai/api", {"code", "data", "deps"}),
    ("credential_ref", "medium", r"\b(?:OPENROUTER|TOGETHER|OPENAI|ANTHROPIC|GROQ|MISTRAL|DEEPSEEK|FIREWORKS|ZAI|GEMINI)"
     r"_API_KEY\b|\bAWS_(?:SECRET_ACCESS_KEY|ACCESS_KEY_ID|SESSION_TOKEN|BEARER_TOKEN_BEDROCK)\b|\bGITHUB_TOKEN\b|"
     r"\bGH_TOKEN\b|\bDFBENCH_(?:SEAL_KEY|OPS_TOKEN)\b", {"code", "dockerfile", "data"}),
    ("credential_value", "high", r"sk-or-v1-[0-9a-f]{20,}|\bsk-[A-Za-z0-9_-]{32,}|\bAKIA[0-9A-Z]{16}\b|"
     r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", {"code", "dockerfile", "data", "deps"}),
    ("scorer_or_pool_path", "medium", r"(?<![\w.-])/artifacts\b|(?<![\w.-])/ledger\b|\bscenarios/snapshots\b|"
     r"\bsnapshot_pool\b|\bdfbench-ops\b|\bseal(?:ed)?[-_]?key\b|\bscore_detail\b|\bprivate[-_ ]pool\b|"
     r"(?<![\w.-])pool/(?:seeds|forts|private)", {"code", "dockerfile", "data"}),
    ("dfhack_direct", "medium", r"\bdfhack(?:-run)?\b|\bRemoteFortressReader\b|:5000\b|\bdfhack\.(?:run|lua)\b",
     {"code", "dockerfile"}),
    ("obfuscation", "medium", r"\b(?:exec|eval)\s*\(.*\b(?:b64decode|a85decode|decompress|unhexlify|fromhex|"
     r"marshal\.loads|codecs\.decode|rot13|atob|fromCharCode)\b|\bmarshal\.loads\s*\(|\b__import__\s*\(\s*['\"]"
     r"(?:socket|subprocess|ctypes)|[A-Za-z0-9+/]{400,}={0,2}", {"code", "data"}),
    ("process_escape", "medium", r"\bctypes\b.*\b(?:CDLL|cdll)\b|\bptrace\b|\bnsenter\b|\bchroot\b|\bmount\s+-|"
     r"\b(?:setns|unshare)\b", {"code", "dockerfile"}),
]
COMPILED = [(k, lvl, re.compile(rx, re.I if k not in ("credential_value",) else 0), kinds) for k, lvl, rx, kinds in RULES]

URL = re.compile(r"\b(?:https?|wss?|ftp|tcp|udp)://([A-Za-z0-9._\-\[\]:]+)")
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?![\d.])")

# a role header ("system prompt:") counts only at the start of a line: mid-sentence it is a harness describing
# its own prompt files (false positive on the first internal submission, 2026-10-28)
INJECTION = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|preceding|all|"
    r"system|the)\b[^.\n]{0,30}\b(?:instructions?|rules?|rubric|prompts?|guidelines|directions)\b|"
    r"\b(?:you are|act as|you're)\s+(?:now\s+)?(?:the|an?)\s+(?:judge|reviewer|adjudicator|grader|evaluator)\b|"
    r"\b(?:output|return|respond with|reply with|emit|answer|print|set|mark)\b[^.\n]{0,25}\b(?:verdict|"
    r"\"?pass\"?\s*(?:verdict|only|$)|assessment\s*[:=]\s*\"?clean|no findings)\b|"
    r"(?:^|[\n>])[ \t\"'*#>`]*(?:system|developer)\s*(?:prompt|message)\s*:|<\s*/?\s*(?:system|im_start|im_end)\b|"
    r"\[/?INST\]|"
    r"\bjudge\b[^.\n]{0,40}\b(?:must|should|will)\b[^.\n]{0,20}\b(?:pass|approve|accept|promote)\b|"
    r"\b(?:pre-?approved|already approved|organi[sz]ers? (?:have )?approved)\b|"
    r"\bend of (?:untrusted|submission|note)\b|<<<\s*(?:END|UNTRUSTED)", re.I)


def _external_host(h):
    h = h.strip("[]").split(":")[0].lower().rstrip(".")
    if not h or h in ALLOWED_HOSTS:
        return None
    try:
        ip = ipaddress.ip_address(h)
        return None if ip.is_loopback or ip.is_unspecified else h
    except ValueError:
        return h


def _public_ip(s):
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_reserved or ip.is_multicast
                or ip.is_link_local)


BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")      # Trojan Source: text that renders unlike it reads


def _plain(text):
    """What a reader sees: NFKC (fullwidth and compatibility forms folded) with format characters (zero-width
    spaces, joiners, bidi controls, soft hyphens) removed, so they can't split a phrase the scan looks for."""
    return "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")


def _hidden_chars(text):
    """'high' for bidi controls, 'medium' for other invisible format characters, else None."""
    if BIDI.search(text):
        return "high"
    if any(unicodedata.category(c) == "Cf" and c not in "\u200d\ufe0f" for c in text):   # ZWJ/VS16: emoji
        return "medium"
    return None


def scan(scan_lines, note, per_kind_file=3, cap=80):
    """scan_lines: [(path, lineno, text)] of added lines in submission/. Returns a list of signals."""
    out, seen = [], {}

    def add(kind, level, path, ln, text, detail=None):
        key = (kind, path)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > per_kind_file:
            return
        out.append({"kind": kind, "level": level, "file": path, "line": ln, "quote": text.strip()[:200],
                    **({"detail": detail} if detail else {})})

    for path, ln, text in scan_lines:
        k = file_kind(path)
        for kind, level, rx, kinds in COMPILED:
            if k in kinds and rx.search(text):
                add(kind, level, path, ln, text)
        if k == "code":
            for m in URL.finditer(text):
                h = _external_host(m.group(1))
                if h:
                    add("external_url", "medium", path, ln, text, h)
            for m in IPV4.finditer(text):
                if _public_ip(m.group(1)) and not re.search(r"(?i)version|__version__|\bv\d", text):
                    add("ip_literal", "medium", path, ln, text, m.group(1))
        hid = _hidden_chars(text)
        if hid:
            add("hidden_unicode", hid, path, ln, text.encode("unicode_escape").decode()[:200])
        if INJECTION.search(text) or INJECTION.search(_plain(text)):
            add("injection", "high", path, ln, text)
    lines = note.split("\n")
    for i, text in enumerate(lines, 1):
        hid = _hidden_chars(text)
        if hid:
            add("hidden_unicode", hid, "NOTE", i, text.encode("unicode_escape").decode()[:200])
        # a phrase split over two lines is still the phrase
        pair = _plain(text + " " + (lines[i] if i < len(lines) else ""))
        if INJECTION.search(text) or INJECTION.search(pair):
            add("injection", "high", "NOTE", i, text)
    return out[:cap], len(out)


def deterministic_signals(contexts, overlaps, deps, declaration_hidden=False):
    """Attribution tripwires computed from the context: the base producer not declared, and heavy line overlap
    with an undeclared prior submission (including the workflow's overlap-scan hits). Neither fires for the
    submitter's own earlier submissions.

    declaration_hidden: Yukon shows a submission's declared dependencies only to its author until it is published,
    so during scoring the formal list is often unavailable (yukon docs/attribution-dag.md). "Not declared" then means
    "not known", so these two signals are medium (reviewer findings, not an automatic hold) and the formal list is
    checked after publication (runner/ci/bin/attribution_verify.py)."""
    out = []
    cap = (lambda lvl: "medium" if lvl == "high" else lvl) if declaration_hidden else (lambda lvl: lvl)
    for c in contexts:
        if c["produced_base"] and not c["declared"] and not c.get("own"):
            # how much of the base producer's own code survives (evidence.mark_base_retention; unknown -> high)
            n, f = c.get("base_retained_lines"), c.get("base_retained_fraction")
            lvl = "high" if n is None or f >= 0.5 or (n >= 30 and f >= 0.3) else "medium"
            kept = "" if n is None else f" (it keeps {n} of the base producer's added lines, {f:.0%})"
            out.append({"kind": "base_producer_undeclared", "level": cap(lvl), "file": "dependencies.json", "line": None,
                        "quote": f"context {c['id']} produced the base this submission starts from{kept}; "
                                 + ("the formal declaration is hidden until publication: check the note"
                                    if declaration_hidden else "not declared")})
    for o in overlaps:
        if o["declared"] or o["produced_base"] or o.get("own"):
            continue      # the submitter's own earlier work isn't undeclared copying (RULES §8)
        if (o["shared_lines"] >= 30 and o["fraction"] >= 0.3) or (o["shared_lines"] >= 20 and o["fraction"] >= 0.5):
            lvl = "high"
        elif o["shared_lines"] >= 8 or o["fraction"] >= 0.1:
            lvl = "medium"
        else:
            continue
        out.append({"kind": "undeclared_overlap", "level": cap(lvl), "file": o["samples"][0]["at"] if o["samples"] else "?",
                    "line": None, "quote": f"{o['shared_lines']} added lines ({o['fraction']:.0%}) also added by "
                    f"undeclared context {o['context_id']}"})
    return out
