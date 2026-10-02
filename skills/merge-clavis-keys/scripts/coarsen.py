#!/usr/bin/env python3
"""Coarsen over-granular categorical states, accepted or rejected by
measurement. Only EXCLUSIVE characters; non-exclusive and numerical
characters are never touched (numerical characters have no bins to merge).

Usage: coarsen.py IN.json OUT.json --neighbours neighbours.json --workdir coarsen/ [--log coarsen-log.json]

neighbours.json, written by the merge agent (or the determinability pass):
  {"Character title": [["label a", "label b"], ...]}        pairs that may merge
  optional "__names__": {"label a|label b": "merged label"}  else "a eller b"-style join is NOT
                                                            invented: the first label wins
Per step the candidate must pass redundancy.py --merge (no pair loses its
last route, no pair with >=3 routes drops below 3, the character keeps >=75 %
of its own power) both against the current key and cumulatively against the
key before any coarsening. Greedy: the merge gaining most confident cells
first. Each accepted step is written as <workdir>/step-NN.json and applied
with apply_coarsen.py; pass the steps to roundtrip.py with --rename in order.
"""
import argparse, importlib.util, itertools, json, os, shutil, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("outp")
ap.add_argument("--neighbours", required=True)
ap.add_argument("--workdir", required=True)
ap.add_argument("--log", default=None)
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
spec_ = importlib.util.spec_from_file_location("redundancy", os.path.join(HERE, "redundancy.py"))
R = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(R)
T = lambda o: next(iter((o.get("title") or {}).values()), "")
load = lambda p: json.load(open(p, encoding="utf-8"))
dump = lambda d, p: json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

NB = load(a.neighbours)
NAMES = NB.pop("__names__", {})
os.makedirs(a.workdir, exist_ok=True)
comp = {}   # (char, merged label) -> set of atomic labels
def atoms(ch, l): return comp.get((ch, l), {l})
def merged_name(parts):
    key = "|".join(sorted(parts))
    return NAMES.get(key) or sorted(parts, key=len)[0]

def candidates(d):
    out = []
    for c in d["characters"]:
        if c.get("type", "exclusive") != "exclusive" or len(c.get("states") or []) < 3: continue
        t = T(c); labs = [T(s) for s in c["states"]]
        if t not in NB: continue
        nb = {frozenset(p) for p in NB[t]}
        for l1, l2 in itertools.combinations(labs, 2):
            if any(frozenset((x, y)) in nb for x in atoms(t, l1) for y in atoms(t, l2)):
                parts = atoms(t, l1) | atoms(t, l2)
                out.append((t, {l1: merged_name(parts), l2: merged_name(parts)}, parts))
    return out

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True); return r.returncode, r.stdout + r.stderr

cur = os.path.join(a.workdir, "step-00.key.json"); shutil.copy(a.inp, cur)
d0, lv0, E0, _ = R.load(cur); sep0, conf0, tot0, pc0 = R.analyse(d0, lv0, E0, {})
pow0 = {T(c): pc0[c["id"]] for c in d0["characters"]}
log, step = [], 0
while True:
    d, lv, E, _ = R.load(cur); sep, conf, tot, pc = R.analyse(d, lv, E, {})
    best = None
    for t, plan, parts in candidates(d):
        sep2, conf2, tot2, pc2 = R.analyse(d, lv, E, {t: plan})
        gain = conf2 - conf
        if gain <= 0: continue
        cid = next(c["id"] for c in d["characters"] if T(c) == t)
        if any(k not in sep2 for k in sep) or any(k not in sep2 for k in sep0): continue
        if any(len(sep[k]) >= 3 and len(sep2.get(k, ())) < 3 for k in sep): continue
        if any(len(sep0[k]) >= 3 and len(sep2.get(k, ())) < 3 for k in sep0): continue
        if pc2[cid] < 0.75 * pc[cid] or pc2[cid] < 0.75 * pow0.get(t, 0): continue
        key = (gain, -(pc[cid] - pc2[cid]))
        if best is None or key > best[0]: best = (key, t, plan, parts, pc[cid], pc2[cid])
    if best is None: break
    step += 1
    (gain, _), t, plan, parts, p1, p2 = best
    planp = os.path.join(a.workdir, f"step-{step:02d}.json"); dump({t: plan}, planp)
    rc, msg = run([sys.executable, os.path.join(HERE, "redundancy.py"), cur, "--merge", planp])
    assert rc == 0 and "NOT AFFORDABLE" not in msg, msg
    nxt = os.path.join(a.workdir, f"step-{step:02d}.key.json")
    rc, msg2 = run([sys.executable, os.path.join(HERE, "apply_coarsen.py"), cur, nxt, planp]); assert rc == 0, msg2
    comp[(t, list(plan.values())[0])] = parts
    log.append({"step": step, "character": t, "merge": sorted(plan), "into": list(plan.values())[0],
                "confident_cells_gained": gain, "character_power": [p1, p2]})
    print(f"step {step:2d}: {t}: {' + '.join(sorted(plan))} -> {list(plan.values())[0]}  (+{gain} cells, power {p1} -> {p2})")
    cur = nxt
shutil.copy(cur, a.outp)
if a.log: dump(log, a.log)
d, lv, E, _ = R.load(a.outp); sep, conf, tot, pc = R.analyse(d, lv, E, {})
print(f"{step} merges; confident cells {conf0}/{tot0} -> {conf}/{tot}; pairs separated {len(sep0)} -> {len(sep)}")
