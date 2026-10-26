# yukon-df:53.16 — DF 53.16 + DFHack 53.16-r2 headless in Docker Desktop

Verified 2026-10-07, including a rebuild from this repo's `docker/` and full-year noop/random/scripted runs on an Apple Silicon Mac (arm64, macOS 27, Docker Desktop 29.8.2, Rosetta x86_64 emulation on).
The repo's own `reset_fort.sh` passes (`READY 823201 pop=7`, ~12 s), `harness.py --selftest` passes, and a full
`smoke.py --only noop` year completes (17 min wall).

## macOS setup (Apple Silicon)
1. Install Docker Desktop. In Settings → General, turn on **"Use Rosetta for x86_64/amd64 emulation on Apple
   Silicon"** (otherwise it falls back to QEMU, which is much slower and less tested with DFHack).
2. In Settings → Resources, give the Docker VM enough memory: **about 1 GB per parallel container, plus 2 GB
   headroom** (DF uses ~0.7 GB at 7 dwarves and grows with the fort; containers are capped with `--memory`).
   CPU: each container uses ~1–1.5 cores, so `--parallel` ≈ cores − 2.
3. Check: `docker run --rm --platform linux/amd64 debian:bookworm-slim uname -m` prints `x86_64`.

Intel Macs and x86_64 Linux run the image natively (faster); the steps below are identical.

## Build

```sh
mkdir -p ~/df-dl && cd ~/df-dl
curl -LO https://www.bay12games.com/dwarves/df_53_16_linux.tar.bz2
curl -L -o dfhack-53.16-r2-Linux-64bit.tar.bz2 \
  https://github.com/DFHack/dfhack/releases/download/53.16-r2/dfhack-53.16-r2-Linux-64bit.tar.bz2
cd /path/to/the/repo          # repo root
docker buildx build --platform linux/amd64 \
  --build-context dl=$HOME/df-dl --build-context harness=. \
  -f docker/Dockerfile -t yukon-df:53.16 --load docker
```

## Run

```sh
docker run -d --name df1 --platform linux/amd64 --security-opt seccomp=unconfined \
  --memory 3g --memory-swap 3g -e OPENROUTER_API_KEY yukon-df:53.16
docker exec df1 bash -c 'mkdir -p df/save && ./reset_fort.sh'
docker exec df1 python3 smoke.py --only noop --runs 1 --out runs/noop1
docker cp df1:/root/dfprobe/runs ./runs
```

### Parallel batches: `docker/batch.sh`
Runs one container per (arm, k), up to `--parallel` at a time, copies each run's outputs to `<out>/<arm>-<k>/`,
and removes the containers. Plain bash 3.2, so it works with macOS's stock shell. Re-running skips completed runs.

```sh
docker/batch.sh --image yukon-df --arms noop,random,scripted --runs 5 --parallel 3 --out runs/my-batch -- --days 60
python3 analyze.py runs/my-batch/*/
```
Arguments after `--` go to `smoke.py` (e.g. `--scenario scenarios/<name>.json`; the scenario and its snapshot
must be in the image, so rebuild the image after adding one).

**Claude on Amazon Bedrock** (instead of OpenRouter): run `bench/bedrock_proxy.py` on the host. It is an
OpenAI-compatible endpoint that calls Claude through the Anthropic SDK's `AnthropicBedrockMantle` client, using
your normal AWS credentials (`AWS_PROFILE`), so no AWS secrets go into the containers:
```sh
uv run --with "anthropic[bedrock]" bench/bedrock_proxy.py --log runs/bedrock-proxy.jsonl &   # 127.0.0.1:8011
docker/batch.sh --arms model2 ... -- --model anthropic/claude-sonnet-5 --base-url http://host.docker.internal:8011/v1
```
Sonnet 5, Sonnet 5.5 and Opus 5.5 are checked. The proxy:
- caches the fixed tools-plus-manual prefix;
- drops sampling parameters;
- sets `effort` to low (`--effort`), like the harness's `CHAT_EXTRA`;
- turns `tool_choice=required` into `auto` plus a one-line instruction for models that reject forced tool use (Opus 5.5, Sonnet 5.5).

Each request's translation, usage and estimated cost (at Anthropic list prices; Bedrock billing may differ) goes
to `--log`. `bench/debrief.py --base-url http://127.0.0.1:8011/v1` uses it too.

**Batch metadata and the comparability key** (`bench/key.py`, `docs/BENCHMARK-v1.md` §1.1): each run writes
`BATCH.json` with a key computed from the files in its image: tool schemas, tool code, manual, observation,
loop, scoring, task, budget. `batch.sh` writes `<out>/BATCH.host.json` with the commit, dirty-tree flag, image
digest and Docker version. Before launching it computes the image's key: it warns if the image was built from a different
tree than the checkout, and refuses to resume into an out dir whose runs came from a different harness
(`DFBENCH_ALLOW_MIXED=1` overrides). At the end it checks that all runs share one key.
`DFBENCH_REQUIRE_CLEAN=1` refuses a dirty tree. Keys are `dfbench/v2.1.1` since the v2.1.1 harness patch (2026-10-14, tag `harness-v2.1.1`; v2.1 froze the same day, tag `harness-v2.1`; it superseded `dfbench/v2`, tag `harness-v2`); `dfbench/v1` (2026-10-10, tag `harness-v1`) results stay on their own board, and `dfbench/v0-dev` / `dfbench/v2-dev` results are provisional.

Each container is its own DF instance (own port 5000, own `pkill` scope), so the repo's single-instance limit goes
away. Run N containers for N parallel runs.

### Embark snapshots: `docker/embark.sh`
Makes a fresh fort from a world seed and site rules in a throwaway container and copies the save to
`scenarios/snapshots/embark-<rules>-<seed>/` (about 1-5 min per fort; `--check` makes it twice and compares).
Details, determinism and pools: `scenarios/README.md`, "Embark snapshots". Copy the snapshots into the image (or
rebuild after generating them) before a batch uses a scenario that names them.

### The `dfai` image (experimental df-ai arm)
`docker/Dockerfile.dfai` compiles DFHack 53.16-r2 and the df-ai fork from pinned commits, applies the two
checksum-verified patches in `research/df-ai/`, and adds `df-ai.plug.so`, its blueprints and the arm's config
(`docker/dfai/df-ai.json`) to an existing `yukon-df` image. Build `yukon-df` first.

```sh
docker buildx build --platform linux/amd64 --build-context harness=. --build-arg BASE=yukon-df \
  -f docker/Dockerfile.dfai -t yukon-df:dfai --load docker
docker run -d --name df_dfai_1 --platform linux/amd64 --security-opt seccomp=unconfined \
  --memory 2g --memory-swap 2g yukon-df:dfai
docker exec df_dfai_1 bash -c 'mkdir -p df/save && python3 smoke.py --only dfai --runs 3 --days 60 --out runs/dfai'
```
The compile stage takes ~6.5 min on an Apple Silicon Mac under Rosetta (`JOBS=3`, the default; higher values
ran libdfhack out of memory at 3 GB). Two `--no-cache` builds gave a bit-identical plugin. Details and the
fairness audit: `research/df-ai-fairness-audit.md`.

## Things the container had to change
| Problem | Fix |
|---|---|
| `start_df.sh` / `gen.sh` use `systemd-run --user`, which doesn't exist in containers | `start_df.sh` here drops it; memory cap moves to `docker run --memory 3g --memory-swap 3g` |
| The `dfhack` launcher runs `setarch -R` (personality ADDR_NO_RANDOMIZE), which Docker's default seccomp blocks, so DF never starts | `--security-opt seccomp=unconfined` (a narrower custom profile that allows `personality(0x0040000)` would also work) |
| No locale: `dfhack-run` prints `locale::facet::_S_create_c_locale` on stderr. The harness merges stderr into stdout, so the `endswith("true")` pause check fails and every advance waits out its full timeout | Generate `en_US.UTF-8`, set `LANG`/`LC_ALL`, `TERM=xterm` |
| DFHack's `overlay` plugin (UI widgets nobody sees here) made a paused DF spin a whole core | `docker/dfhack-onMapLoad.init` → `df/dfhack-config/init/onMapLoad.init`: `disable overlay` once a fort loads (title, world gen and embark keep it) |
| `env.sh` no-sudo sysroot | Not needed; deps come from apt (`ldd dwarfort` resolves everything) |

## Measured performance (Rosetta, 1 container)
- ~1,000 game ticks/s at 7 dwarves (1 day = 1,200 ticks); ~1.06 CPU cores; ~700 MB RSS.
- With overlay off (2026-10-22 image): ~1,200 ticks/s on the first 112 days of noop, 736 ticks/s over a full
  noop year, 600 over a full automation year (n=3 each, P=3; 598 and 472 before); paused ~0.25 core.
- No-action year (7→13 dwarves): 1,014 s wall.
- Model runs add LLM latency per decision on top of this.
