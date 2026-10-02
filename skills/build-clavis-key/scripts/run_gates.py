#!/usr/bin/env python3
"""Run every gate of build-clavis-key Phase 4 on a final key and write gates.md.
One command, one table, one exit code.

Usage:
  run_gates.py KEY.json --csv species.csv --sources work --out leveranse \
      [--spec merge/spec.json --alias merge/alias.json --removed merge/removed.json --rename merge/coarsen/step-01.json ...]
      [--source-keys merge/src/*.json] [--location "^(Utbredelse|Forekomst|Occur|Distribution)"]
      [--run-start work/run-start.txt --match <sources folder name>]

Gates:
  1 verify.py                       PASS required
  2 check_bins.py                   no defects (bins and numerical ranges)
  3 claims audit per source         0 unsupported, 0 unaccounted; needs <sources>/<src>/claims.jsonl,
                                    provenance.jsonl, skipped.jsonl and the audited key <src>/*.audited.json
  4 roundtrip.py                    0 LOST (needs --spec and --source-keys)
  5 redundancy.py                   reported: pairs separated, inseparable pairs listed
  6 geography                       no pair separated only by a location character
  7 coverage                        reported: species on the list present in the key
  8 token_report.py                 reported, when --run-start is given (Claude Code only)
Exit 1 if gate 1, 2, 3, 4 or 6 fails.
"""
import argparse, collections, csv, datetime, glob, itertools, json, os, re, subprocess, sys

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("key"); ap.add_argument("--csv", required=True); ap.add_argument("--sources", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--spec"); ap.add_argument("--alias"); ap.add_argument("--removed"); ap.add_argument("--rename", action="append", default=[])
ap.add_argument("--source-keys", nargs="*", default=[])
ap.add_argument("--location", default=r"^(Utbredelse|Forekomst|Occur|Distribution|Verbreitung|Voorkomen)")
ap.add_argument("--run-start"); ap.add_argument("--match")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
os.makedirs(a.out, exist_ok=True)
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True); return r.returncode, (r.stdout + r.stderr).strip()
def save(name, text): open(os.path.join(a.out, name), "w", encoding="utf-8").write(text + "\n")
G = {}

rc, out = run([sys.executable, os.path.join(REPO, "tools/verify.py"), a.key]); save("gate1-verify.txt", out)
G[1] = (rc == 0, out.splitlines()[0] if out else "")
rc, out = run([sys.executable, os.path.join(REPO, "skills/audit-clavis-key/scripts/check_bins.py"), a.key]); save("gate2-check_bins.txt", out)
G[2] = (rc == 0, out.splitlines()[-1] if out else "")

g3, ok3 = [], True
for cl in sorted(glob.glob(os.path.join(a.sources, "*", "claims.jsonl"))):
    sdir = os.path.dirname(cl); src = os.path.basename(sdir)
    keys = sorted(glob.glob(os.path.join(sdir, "*.audited.json"))) or sorted(glob.glob(os.path.join(sdir, "*.json")))
    prov = [p for p in (os.path.join(sdir, "provenance.audited.jsonl"), os.path.join(sdir, "provenance.jsonl")) if os.path.exists(p)]
    skip = [p for p in (os.path.join(sdir, "skipped.audited.jsonl"), os.path.join(sdir, "skipped.jsonl")) if os.path.exists(p)]
    if not keys or not prov:
        g3.append((src, "no audited key or provenance", None, None)); ok3 = False; continue
    rep = os.path.join(a.out, f"gate3-{src}.claims-audit.md")
    cmd = [sys.executable, os.path.join(REPO, "skills/harvest-claims/scripts/claims_vs_key.py"), cl, keys[-1], "--provenance", prov[0], "--out", rep]
    if skip: cmd += ["--skipped", skip[0]]
    rc, out = run(cmd)
    m = re.search(r"A: (\d+) unsupported statements; B: (\d+) unaccounted claims", out)
    u, g = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    g3.append((src, "", u, g)); ok3 = ok3 and rc == 0
G[3] = (ok3 and bool(g3), "; ".join(f"{s}: {u} unsupported, {g} unaccounted" if u is not None else f"{s}: {why}" for s, why, u, g in g3) or "no claims files found")

if a.spec and a.source_keys:
    cmd = [sys.executable, os.path.join(REPO, "skills/merge-clavis-keys/scripts/roundtrip.py"), "--merged", a.key, "--spec", a.spec, "--csv", a.csv, "--report", os.path.join(a.out, "gate4-roundtrip.md")]
    if a.alias: cmd += ["--alias", a.alias]
    if a.removed: cmd += ["--removed", a.removed]
    for r in a.rename: cmd += ["--rename", r]
    rc, out = run(cmd + a.source_keys)
    sumline = next((l for l in out.splitlines() if l.startswith("SUM")), out.splitlines()[-1] if out else "")
    G[4] = (rc == 0, sumline)
else:
    G[4] = (True, "skipped: no --spec/--source-keys (single-source key)")

rc, out = run([sys.executable, os.path.join(REPO, "skills/merge-clavis-keys/scripts/redundancy.py"), a.key]); save("gate5-redundancy.txt", out)
G[5] = (True, " | ".join(out.splitlines()[:2]))

# geography: pairs separated only by location characters
d = json.load(open(a.key, encoding="utf-8"))
T = lambda o: next(iter((o.get("title") or {}).values()), "")
sys.path.insert(0, os.path.join(REPO, "skills/merge-clavis-keys/scripts"))
import importlib.util
spec_ = importlib.util.spec_from_file_location("redundancy", os.path.join(REPO, "skills/merge-clavis-keys/scripts/redundancy.py"))
R = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(R)
dd, lv, E, taxa = R.load(a.key); sep, *_ = R.analyse(dd, lv, E, {})
loc = {c["id"] for c in dd["characters"] if re.search(a.location, T(c), re.I)}
only_geo = [(taxa[x]["scientificName"], taxa[y]["scientificName"]) for (x, y), routes in sep.items() if routes and routes <= loc]
G[6] = (not only_geo, f"pairs separated only by location: {len(only_geo)}" + (": " + "; ".join(f"{x} / {y}" for x, y in only_geo) if only_geo else "") + f"; location characters: {len(loc)}")

keep = [r["scientificName"].strip() for r in csv.DictReader(open(a.csv, encoding="utf-8-sig")) if r.get("scientificName", "").strip()]
inkey = {taxa[l]["scientificName"] for l in lv}
missing = [k for k in keep if k not in inkey]
G[7] = (True, f"{len(inkey & set(keep))} of {len(keep)} listed species in the key" + (f"; not covered: {', '.join(missing)}" if missing else ""))

if a.run_start and os.path.exists(a.run_start):
    start = open(a.run_start).read().strip()[:16]  # token_report wants "YYYY-MM-DD HH:MM"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cmd = [sys.executable, os.path.join(REPO, "tools/token_report.py"), "--since", start, "--until", now, "--out", os.path.join(a.out, "tokens.md")]
    if a.match: cmd += ["--match", a.match]
    rc, out = run(cmd)
    tot = next((l for l in out.splitlines() if l.startswith("| **total**")), "")
    G[8] = (True, f"{start} to {now}; " + tot.replace("|", " ").strip())
else:
    G[8] = (True, "not measured (no --run-start)")

names = {1: "verify.py", 2: "check_bins.py", 3: "claims audit per source", 4: "round-trip", 5: "redundancy", 6: "geography", 7: "coverage", 8: "tokens and cost"}
required = {1, 2, 3, 4, 6}
L = [f"# Gates for {os.path.basename(a.key)}", "", "| gate | result | numbers |", "|---|---|---|"]
for k in sorted(G):
    ok, txt = G[k]
    res = ("PASS" if ok else "FAIL") if k in required else "reported"
    L.append(f"| {k}. {names[k]} | {res} | {txt} |")
L += ["", "Details: gate1-verify.txt, gate2-check_bins.txt, gate3-*.claims-audit.md, gate4-roundtrip.md, gate5-redundancy.txt, tokens.md."]
save("gates.md", "\n".join(L))
print("\n".join(L))
sys.exit(0 if all(G[k][0] for k in required) else 1)
