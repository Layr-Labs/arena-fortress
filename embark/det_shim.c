// det_shim.c: LD_PRELOAD shim for DF determinism experiments (research/determinism.md).
//
//   gcc -O2 -shared -fPIC -o det_shim.so embark/det_shim.c -ldl
//   DET_MODE=count|fix  DET_SEED=<n>  DET_TIME=<unix seconds>  DET_LOG=<file>  LD_PRELOAD=det_shim.so ./dwarfort ...
//
// Only acts inside the dwarfort process (any other process that inherits LD_PRELOAD passes straight through).
// DET_MODE=count (default): call the real functions and count the calls.
// DET_MODE=fix: make the nondeterministic inputs DF imports deterministic:
//   std::random_device::_M_getval()   -> a splitmix64 stream seeded from DET_SEED (default 1)
//   time(), gettimeofday()            -> DET_TIME (default 1767225600 = 2026-01-01) plus a virtual clock that advances
//                                        1 ms per call, so loops that wait on the wall clock still make progress while
//                                        the values stay a pure function of the call sequence. CLOCK_MONOTONIC (SDL
//                                        frame timing) is not touched.
// Always counted: pthread_create (threads DF starts) and rand().
// Counts go to DET_LOG (appended, one JSON line per thread start and at exit) if set, else stderr. DF is often killed
// with -9 (reset_fort.sh), so DET_STATUS (if set) is also rewritten with the current counts every 1024 clock calls.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static int active = -1, fix = 0;
static uint64_t sm_state = 1, vclock_ms = 0, t0 = 1767225600ULL;
static unsigned long n_rd = 0, n_time = 0, n_gtod = 0, n_thread = 0, n_rand = 0;
static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;

static int is_active(void) {
  if (active >= 0) return active;
  char exe[512] = {0};
  ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
  active = n > 0 && strstr(exe, "dwarfort") != NULL;
  const char *m = getenv("DET_MODE");
  fix = active && m && !strcmp(m, "fix");
  const char *s = getenv("DET_SEED");
  if (s) sm_state = strtoull(s, NULL, 10);
  const char *t = getenv("DET_TIME");
  if (t) t0 = strtoull(t, NULL, 10);
  return active;
}

static uint64_t splitmix64(void) {
  uint64_t z = (sm_state += 0x9E3779B97F4A7C15ULL);
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
  z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
  return z ^ (z >> 31);
}

static unsigned long n_tr, n_tr_ui;
static void dump_hist(void);
static void pause_edge(void);

static void write_counts(FILE *f) {
  fprintf(f, "{\"det_mode\": \"%s\", \"pid\": %d, \"random_device\": %lu, \"time\": %lu, \"gettimeofday\": %lu, "
             "\"rand\": %lu, \"pthread_create\": %lu, \"mt_trandom\": %lu, \"mt_trandom_ui\": %lu}\n",
          fix ? "fix" : "count", (int)getpid(), n_rd, n_time, n_gtod, n_rand, n_thread, n_tr, n_tr_ui);
}

static void maybe_status(void) {   // caller holds mu
  pause_edge();
  if (((n_time + n_gtod) & 1023) != 0) return;
  if (((n_time + n_gtod) & 65535) == 0) dump_hist();
  const char *st = getenv("DET_STATUS");
  if (!st) return;
  FILE *f = fopen(st, "w");
  if (f) { write_counts(f); fclose(f); }
}

static uint64_t vnow_ms(void) {   // caller holds mu
  vclock_ms += 1;
  return t0 * 1000ULL + vclock_ms;
}

// std::random_device::_M_getval() (libstdc++, GLIBCXX_3.4.18): unsigned int, `this` in rdi.
unsigned int _ZNSt13random_device9_M_getvalEv(void *self) {
  static unsigned int (*real)(void *) = NULL;
  if (!real) real = (unsigned int (*)(void *))dlsym(RTLD_NEXT, "_ZNSt13random_device9_M_getvalEv");
  if (is_active()) {
    pthread_mutex_lock(&mu); n_rd++;
    if (fix) { unsigned int v = (unsigned int)splitmix64(); pthread_mutex_unlock(&mu); return v; }
    pthread_mutex_unlock(&mu);
  }
  return real(self);
}

time_t time(time_t *tloc) {
  static time_t (*real)(time_t *) = NULL;
  if (!real) real = (time_t (*)(time_t *))dlsym(RTLD_NEXT, "time");
  if (is_active()) {
    pthread_mutex_lock(&mu); n_time++; maybe_status();
    if (fix) { time_t v = (time_t)(vnow_ms() / 1000ULL); pthread_mutex_unlock(&mu); if (tloc) *tloc = v; return v; }
    pthread_mutex_unlock(&mu);
  }
  return real(tloc);
}

int gettimeofday(struct timeval *tv, void *tz) {
  static int (*real)(struct timeval *, void *) = NULL;
  if (!real) real = (int (*)(struct timeval *, void *))dlsym(RTLD_NEXT, "gettimeofday");
  if (is_active()) {
    pthread_mutex_lock(&mu); n_gtod++; maybe_status();
    if (fix && tv) {
      uint64_t ms = vnow_ms(); pthread_mutex_unlock(&mu);
      tv->tv_sec = (time_t)(ms / 1000ULL); tv->tv_usec = (suseconds_t)((ms % 1000ULL) * 1000ULL);
      return 0;
    }
    pthread_mutex_unlock(&mu);
  }
  return real(tv, tz);
}

int rand(void) {
  static int (*real)(void) = NULL;
  if (!real) real = (int (*)(void))dlsym(RTLD_NEXT, "rand");
  if (is_active()) { pthread_mutex_lock(&mu); n_rand++; pthread_mutex_unlock(&mu); }
  return real();
}

int pthread_create(pthread_t *th, const pthread_attr_t *attr, void *(*fn)(void *), void *arg) {
  static int (*real)(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *) = NULL;
  if (!real) real = (int (*)(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *))dlsym(RTLD_NEXT, "pthread_create");
  if (is_active()) {
    Dl_info di; const char *who = "?";
    if (dladdr((void *)fn, &di) && di.dli_fname) who = di.dli_fname;
    // std::thread: the start routine is libstdc++'s trampoline and arg is the _State_impl, whose vtable names (or, in
    // a stripped binary, locates) the callable. Record the vtable's object file, symbol and address.
    const char *vfile = "", *vsym = "";
    void *vt = NULL;
    if (strstr(who, "libstdc++") && arg) {
      Dl_info dv;
      vt = *(void **)arg;
      if (dladdr(vt, &dv)) { vfile = dv.dli_fname ? dv.dli_fname : ""; vsym = dv.dli_sname ? dv.dli_sname : ""; }
    }
    pthread_mutex_lock(&mu); unsigned long nt = ++n_thread; uint64_t vc = vclock_ms; pthread_mutex_unlock(&mu);
    const char *log = getenv("DET_LOG");
    FILE *f = log ? fopen(log, "a") : stderr;
    if (f) {
      fprintf(f, "{\"det_thread\": %lu, \"start_routine_in\": \"%s\", \"state_vtable\": \"%p\", \"vtable_in\": \"%s\", "
                 "\"vtable_sym\": \"%s\", \"clock_calls\": %lu, \"vclock\": %lu}\n",
              nt, who, vt, vfile, vsym, n_time + n_gtod, (unsigned long)vc);
      if (log) fclose(f);
    }
  }
  return real(th, attr, fn, arg);
}

// ---- DF's main RNG (g_src/random.cpp), interposed: every caller reaches it through a PLT (dwarfort and libg_src_lib)
// DET_TRANDOM=count: histogram of draws by caller (return address) and by pause state, dumped to DET_TRANDOM_LOG with
//   the status file. DET_TRANDOM=split: draws on the top-level buffer (mt_cur_buffer 0) that come from the UI layer go
//   to a private stream instead of DF's buffer, so the simulation's stream depends only on the simulation. UI = any
//   caller inside libg_src_lib.so (g_src: graphics, interface, music, enabler), any caller listed in DET_UI_SITES
//   (comma-separated hex return addresses), and, with DET_UI_PAUSED=1, any draw while the game is paused.
// Addresses: DF 53.16 classic Linux (md5 6cf8b7cc..., non-PIE): mt_cur_buffer 0x24dd6e2, pause_state 0x297f2da.
#define A_MT_CUR 0x24dd6e2UL
#define A_PAUSE 0x297f2daUL
#define HSIZE 16384
static struct { uintptr_t pc; unsigned long paused, running, seeded; } hist[HSIZE];
static int tr_mode = -1;   // 0 off, 1 count, 2 split
static uintptr_t g_lo = 0, g_hi = 0;
static uintptr_t ui_sites[256]; static int n_ui = 0; static int ui_paused = 0;
static uint64_t ui_state = 0x5eed5eed5eedULL;

static void tr_init(void) {
  if (tr_mode >= 0) return;
  const char *m = getenv("DET_TRANDOM");
  tr_mode = !is_active() || !m ? 0 : !strcmp(m, "simroot") ? 3 : !strcmp(m, "split") ? 2 : !strcmp(m, "count") ? 1 : 0;
  FILE *maps = fopen("/proc/self/maps", "r"); char line[512];   // libg_src_lib.so's mappings = the g_src UI layer
  while (maps && fgets(line, sizeof line, maps)) {
    if (!strstr(line, "libg_src_lib")) continue;
    unsigned long lo, hi; if (sscanf(line, "%lx-%lx", &lo, &hi) == 2) { if (!g_lo || lo < g_lo) g_lo = lo; if (hi > g_hi) g_hi = hi; }
  }
  if (maps) fclose(maps);
  const char *s = getenv("DET_UI_SITES");
  while (s && *s && n_ui < 256) { ui_sites[n_ui++] = (uintptr_t)strtoull(s, (char **)&s, 16); if (*s == ',') s++; }
  ui_paused = getenv("DET_UI_PAUSED") && !strcmp(getenv("DET_UI_PAUSED"), "1");
}

static void dump_simroot(void);
static void dump_hist(void) {   // caller holds mu
  const char *p = getenv("DET_TRANDOM_LOG");
  if (p && tr_mode == 3) { dump_simroot(); return; }
  if (!p || tr_mode != 1) return;
  FILE *f = fopen(p, "w"); if (!f) return;
  fprintf(f, "{\"libg_lo\": \"%lx\", \"libg_hi\": \"%lx\", \"draws\": %lu}\n", (unsigned long)g_lo, (unsigned long)g_hi, n_tr);
  for (int i = 0; i < HSIZE; i++)
    if (hist[i].pc)
      fprintf(f, "{\"pc\": \"%lx\", \"paused\": %lu, \"running\": %lu, \"seeded\": %lu}\n", (unsigned long)hist[i].pc,
              hist[i].paused, hist[i].running, hist[i].seeded);
  fclose(f);
}

// DET_PAUSE_DUMP=DIR (with DET_TRANDOM=count): on every unpaused -> paused edge, write the cumulative histogram to
// DIR/pause-<n>.jsonl with the game tick, so per-tick draws per call site can be diffed between replays.
#define A_YEAR 0x297f404UL   /* cur_year, int32 (symbols.xml, md5 6cf8b7cc...) */
#define A_YTICK 0x297f3fcUL  /* cur_year_tick, int32 */
static int last_paused = -1; static unsigned long n_edges = 0;
static void pause_edge(void) {   // caller holds mu
  if (tr_mode != 1 || !getenv("DET_PAUSE_DUMP")) return;
  int p = *(volatile uint8_t *)A_PAUSE != 0;
  if (p && last_paused == 0) {
    char path[600];
    snprintf(path, sizeof path, "%s/pause-%05lu.jsonl", getenv("DET_PAUSE_DUMP"), ++n_edges);
    FILE *f = fopen(path, "w");
    if (f) {
      long tick = (long)*(volatile int32_t *)A_YEAR * 403200L + *(volatile int32_t *)A_YTICK;
      fprintf(f, "{\"edge\": %lu, \"abs_tick\": %ld, \"draws\": %lu}\n", n_edges, tick, n_tr);
      for (int i = 0; i < HSIZE; i++)
        if (hist[i].pc) fprintf(f, "{\"pc\": \"%lx\", \"n\": %lu}\n", (unsigned long)hist[i].pc, hist[i].running + hist[i].paused);
      fclose(f);
    }
  }
  last_paused = p;
}

// DET_TRANDOM=simroot: while the game runs, a top-level draw (mt_cur_buffer 0) whose call stack doesn't pass through a
// simulation root goes to the private stream. Found by det_sites.py: fn 0x2064b80 draws for both the per-tick world
// update (fn 0xcd1c70) and, on rendered frames, the UI (fn 0x80a6a0 from the frame loop, fn 0xde3b30 the fortress
// viewscreen), so the number of sim-stream draws per tick depended on frame timing. DET_SIM_ROOTS overrides the root
// ranges ("lo-hi,lo-hi" hex). Draws while paused (DFHack-driven actions between advances) stay on DF's stream.
// Every running top-level draw is backtraced (slow: a proof of mechanism, see research/determinism.md for the cost).
// DET_SIMROOT_LOG: per caller pc, how many draws were classified sim / UI (written with the status file).
#include <execinfo.h>
static uintptr_t root_lo[16], root_hi[16]; static int n_roots = 0;
#define PCSZ 8192
static struct { uintptr_t pc; uint32_t sim, ui; } pcv[PCSZ];

static void roots_init(void) {
  const char *s = getenv("DET_SIM_ROOTS");
  if (!s) s = "1282170-1282190";   // the mainloop() thunk (dwarfort dynsym _Z8mainloopv, 30 bytes): every sim/logic frame runs under it
  while (*s && n_roots < 16) {
    root_lo[n_roots] = (uintptr_t)strtoull(s, (char **)&s, 16);
    if (*s == '-') s++;
    root_hi[n_roots] = (uintptr_t)strtoull(s, (char **)&s, 16);
    n_roots++;
    if (*s == ',') s++;
  }
  void *warm[2]; backtrace(warm, 2);   // the first backtrace() loads libgcc_s: do it outside the hot path
}

// DET_BT_PCS="lo-hi": for draws whose caller pc is in this range, keep each distinct call stack (up to 128) with a
// count and its verdict, dumped with DET_TRANDOM_LOG. Default: fn 0x2064b80 (the routine shared by sim and UI).
#define N_STACKSIG 128
static struct { uint64_t h; unsigned long n; int sim, depth; uintptr_t fr[24]; } sigs[N_STACKSIG];
static int n_sigs = 0; static uintptr_t btlo = 0x2064b80, bthi = 0x2068570; static int bt_init = 0;

static int stack_in_sim(uintptr_t pc) {
  void *bt[48];
  int n = backtrace(bt, 48);
  int sim = 0;
  for (int i = 2; i < n && !sim; i++)
    for (int r = 0; r < n_roots; r++)
      if ((uintptr_t)bt[i] >= root_lo[r] && (uintptr_t)bt[i] < root_hi[r]) { sim = 1; break; }
  if (!bt_init) {
    bt_init = 1;
    const char *s = getenv("DET_BT_PCS");
    if (s) { btlo = (uintptr_t)strtoull(s, (char **)&s, 16); if (*s == '-') s++; bthi = (uintptr_t)strtoull(s, NULL, 16); }
  }
  if (pc >= btlo && pc < bthi) {
    uint64_t h = 1469598103934665603ULL;
    for (int i = 2; i < n; i++) h = (h ^ (uint64_t)(uintptr_t)bt[i]) * 1099511628211ULL;
    int j = 0;
    while (j < n_sigs && sigs[j].h != h) j++;
    if (j == n_sigs && n_sigs < N_STACKSIG) {
      sigs[j].h = h; sigs[j].sim = sim; sigs[j].depth = n - 2 < 24 ? n - 2 : 24;
      for (int i = 0; i < sigs[j].depth; i++) sigs[j].fr[i] = (uintptr_t)bt[i + 2];
      n_sigs++;
    }
    if (j < n_sigs) sigs[j].n++;
  }
  return sim;
}

static unsigned long n_bt = 0;

static void dump_simroot(void) {   // caller holds mu: pcs that drew for the UI while running, and the totals
  FILE *f = fopen(getenv("DET_TRANDOM_LOG"), "w"); if (!f) return;
  fprintf(f, "{\"draws_running_top\": %lu, \"to_private\": %lu, \"backtraces\": %lu}\n", n_tr, n_tr_ui, n_bt);
  for (int i = 0; i < PCSZ; i++)
    if (pcv[i].pc && pcv[i].ui)
      fprintf(f, "{\"pc\": \"%lx\", \"sim\": %u, \"ui\": %u}\n", (unsigned long)pcv[i].pc, pcv[i].sim, pcv[i].ui);
  for (int j = 0; j < n_sigs; j++) {
    fprintf(f, "{\"stack\": %d, \"n\": %lu, \"sim\": %d, \"frames\": [", j, sigs[j].n, sigs[j].sim);
    for (int i = 0; i < sigs[j].depth; i++) fprintf(f, "%s\"%lx\"", i ? ", " : "", (unsigned long)sigs[j].fr[i]);
    fprintf(f, "]}\n");
  }
  fclose(f);
}

uint32_t _Z10mt_trandomv(void) {
  static uint32_t (*real)(void) = NULL;
  if (!real) real = (uint32_t (*)(void))dlsym(RTLD_NEXT, "_Z10mt_trandomv");
  if (tr_mode < 0) { tr_init(); if (tr_mode == 3) roots_init(); }
  if (tr_mode == 0) return real();
  if (tr_mode == 3) {
    uintptr_t pc3 = (uintptr_t)__builtin_return_address(0);
    if (*(volatile int16_t *)A_MT_CUR != 0 || *(volatile uint8_t *)A_PAUSE) return real();
    unsigned h = (unsigned)((pc3 >> 2) * 2654435761u) & (PCSZ - 1);
    pthread_mutex_lock(&mu);
    n_tr++;
    for (int i = 0; i < PCSZ && pcv[h].pc && pcv[h].pc != pc3; i++) h = (h + 1) & (PCSZ - 1);
    if (!pcv[h].pc) pcv[h].pc = pc3;
    // no per-pc caching: a shared routine can be called from the UI once in hundreds of ticks (fn 0x2064b80)
    n_bt++;
    int sim = stack_in_sim(pc3);
    if (sim) pcv[h].sim++; else pcv[h].ui++;
    if (sim) { pthread_mutex_unlock(&mu); return real(); }
    n_tr_ui++;
    uint64_t z = (ui_state += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL; z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    pthread_mutex_unlock(&mu);
    return (uint32_t)(z ^ (z >> 31));
  }
  uintptr_t pc = (uintptr_t)__builtin_return_address(0);
  int16_t cur = *(volatile int16_t *)A_MT_CUR;
  int paused = *(volatile uint8_t *)A_PAUSE != 0;
  pthread_mutex_lock(&mu);
  n_tr++;
  if (tr_mode == 1) {
    unsigned h = (unsigned)((pc >> 2) * 2654435761u) & (HSIZE - 1);
    for (int i = 0; i < HSIZE && hist[h].pc && hist[h].pc != pc; i++) h = (h + 1) & (HSIZE - 1);
    if (!hist[h].pc) hist[h].pc = pc;
    if (hist[h].pc == pc) { if (cur) hist[h].seeded++; else if (paused) hist[h].paused++; else hist[h].running++; }
    if ((n_tr & 0xfffff) == 0) dump_hist();
    pthread_mutex_unlock(&mu);
    return real();
  }
  int ui = 0;
  if (cur == 0) {
    ui = (pc >= g_lo && pc < g_hi) || (ui_paused && paused);
    for (int i = 0; !ui && i < n_ui; i++) ui = ui_sites[i] == pc;
  }
  if (ui) {
    n_tr_ui++;
    uint64_t z = (ui_state += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL; z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    pthread_mutex_unlock(&mu);
    return (uint32_t)(z ^ (z >> 31));
  }
  pthread_mutex_unlock(&mu);
  return real();
}

__attribute__((destructor)) static void report(void) {
  if (active != 1) return;
  const char *log = getenv("DET_LOG");
  FILE *f = log ? fopen(log, "a") : stderr;
  if (!f) return;
  write_counts(f);
  if (log) fclose(f);
}
