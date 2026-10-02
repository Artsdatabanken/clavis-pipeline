#!/usr/bin/env python3
"""Turn claims into statements, deterministically, given a character design.

Usage:
  score_claims.py claims.jsonl design.json --out scored.json [--lang nb] [--residue residue.md]

design.json is what the digitizer writes instead of an assignment map:
{
  "taxa": [{"scientificName": "Sorex minutus", "vernacularName": {"nb": "dvergspissmus"}}, ...],
  "characters": [
    {"key": "tail_ratio", "title": {"nb": "Halelengde i forhold til kroppslengden"},
     "type": "numerical", "unit": "%",
     "traits": ["halelengde i forhold til kroppen", "hale/kropp"]},
    {"key": "belly", "title": {"nb": "Bukfarge"}, "type": "exclusive",
     "states": [{"key": "white", "title": {"nb": "hvit"}, "values": ["hvit", "hvitaktig", "white"]},
                {"key": "grey",  "title": {"nb": "grå"},  "values": ["grå", "gråaktig"]}],
     "traits": ["bukfarge", "undersidens farge"]},
    ...
  ],
  "frequency_table": "optional path; default skills/harvest-claims/references/frequency-table.json"
}

Rules (all mechanical):
  * a claim belongs to a character when its normalized trait equals one of the
    character's `traits` (exact after normalization, no fuzzy matching)
  * numerical character: the claim must carry `value_num`; the statement is
    value [min, max] (an open upper bound becomes the character's max, an
    open lower bound its min; the design may set `min`/`max`, else they are
    taken from the data). Several claims for one taxon -> the union of ranges.
  * categorical character: each `values` entry is matched against the claim's
    normalized value by equality, or by whole-word containment when the claim
    value lists alternatives ("hvit eller grå" matches both states);
    frequency = frequency_table[qualifier]; with several matched states the
    first gets the qualifier's frequency and the others the `_secondary` one
  * non-exclusive characters: every matched state gets its frequency; nothing
    is implied about unmatched states
  * exclusive characters: unmatched states are NOT written (zero is implied by
    the presence of a statement on a sibling state); see docs on size
  * a claim that matches no character, or matches a character but no state,
    goes to the residue list for the digitizer to decide: add a state, add a
    `values` synonym, or skip with a reason.

Outputs: scored.json = {"characters": [...Clavis characters with fresh ids...],
"taxa": [...], "statements": [...], "provenance": [...]}; the digitizer's
generator merges it into the key. residue.md lists unmatched claims.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_FREQ = HERE.parent.parent / "harvest-claims" / "references" / "frequency-table.json"


def text(x):
    return " ".join(str(v) for v in x.values()) if isinstance(x, dict) else str(x or "")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    return re.sub(r"[\s\-–—/,;:.()]+", " ", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("claims", type=Path)
    ap.add_argument("design", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--residue", type=Path)
    ap.add_argument("--lang", default=None)
    a = ap.parse_args()

    claims = [json.loads(l) for l in a.claims.read_text(encoding="utf-8").splitlines() if l.strip()]
    design = json.loads(a.design.read_text(encoding="utf-8"))
    ft_path = Path(design.get("frequency_table") or DEFAULT_FREQ)
    ft = json.loads(ft_path.read_text(encoding="utf-8"))
    lang = a.lang or next(iter(design["characters"][0]["title"])) if design.get("characters") else "en"

    taxa_out, tid = [], {}
    for t in design["taxa"]:
        node = {"id": "taxon:" + uuid.uuid4().hex, "scientificName": t["scientificName"]}
        for k in ("vernacularName", "externalReference", "label"):
            if k in t:
                node[k] = t[k]
        taxa_out.append(node)
        tid[norm(t["scientificName"])] = node["id"]

    chars_out, trait_index = [], {}
    state_index = {}  # char key -> list of (state id, normalized values)
    for c in design["characters"]:
        node = {"id": "character:" + uuid.uuid4().hex, "title": c["title"], "type": c.get("type", "exclusive")}
        if node["type"] == "numerical":
            node["unit"] = c.get("unit", "")
            node["stepSize"] = c.get("stepSize", 1)
            if "min" in c:
                node["min"] = c["min"]
            if "max" in c:
                node["max"] = c["max"]
        else:
            node["states"] = []
            state_index[c["key"]] = []
            for s in c["states"]:
                sn = {"id": "state:" + uuid.uuid4().hex, "title": s["title"]}
                node["states"].append(sn)
                vals = {norm(v) for v in s.get("values", [])} | {norm(v) for v in s["title"].values()}
                state_index[c["key"]].append((sn["id"], vals))
        chars_out.append(node)
        c["_id"] = node["id"]
        for tr in c.get("traits", []):
            trait_index.setdefault(norm(tr), []).append(c)

    stmts, prov, residue = [], [], []
    numeric_acc = defaultdict(lambda: defaultdict(list))  # (taxon id, char id) -> [(lo, hi, claim id)]
    cat_acc = defaultdict(lambda: defaultdict(list))      # (taxon id, char id) -> state id -> [(freq, claim id)]
    for cl in claims:
        if cl.get("observable") is False:
            continue
        t = tid.get(norm(cl["taxon"]))
        if not t:
            residue.append((cl, "taxon not in design"))
            continue
        cands = trait_index.get(norm(cl["trait"]))
        if not cands:
            residue.append((cl, "no character has this trait"))
            continue
        placed = False
        for c in cands:
            if c.get("type") == "numerical":
                vn = cl.get("value_num")
                if not vn:
                    continue
                numeric_acc[(t, c["_id"])]["r"].append((vn[0], vn[1], cl["id"]))
                placed = True
            else:
                v = norm(cl["value"])
                words = f" {v} "
                hit = [(sid, vals) for sid, vals in state_index[c["key"]] if v in vals or any(f" {x} " in words for x in vals if x)]
                if not hit:
                    continue
                q = cl.get("qualifier", "unspecified")
                f0 = ft.get(q, 1.0)
                f1 = ft.get("_secondary", {}).get(q, 1.0) if q in ft.get("_secondary", {}) else ft["_secondary"].get("or", 1.0)
                for k, (sid, _) in enumerate(hit):
                    cat_acc[(t, c["_id"])][sid].append((f0 if k == 0 or c.get("type") == "non-exclusive" else f1, cl["id"]))
                placed = True
        if not placed:
            residue.append((cl, "character found, no state matches the value (add a state or a synonym, or skip with a reason)"))

    # numerical: union of each taxon's ranges; an open side closes at the
    # character's min/max from the design, else at the extreme over all taxa
    # with a known bound, else the claim goes to the residue
    known_lo, known_hi = defaultdict(list), defaultdict(list)
    for (t, cid), d in numeric_acc.items():
        for lo, hi, _ in d["r"]:
            if lo is not None: known_lo[cid].append(lo)
            if hi is not None: known_hi[cid].append(hi)
    for (t, cid), d in numeric_acc.items():
        rs = d["r"]
        c = next(x for x in chars_out if x["id"] == cid)
        los = [lo for lo, hi, _ in rs if lo is not None]
        his = [hi for lo, hi, _ in rs if hi is not None]
        lo = min(los) if los else c.get("min", min(known_lo[cid]) if known_lo[cid] else None)
        hi = max(his) if his else c.get("max", max(known_hi[cid]) if known_hi[cid] else None)
        tname = next(x["scientificName"] for x in taxa_out if x["id"] == t)
        if lo is not None and hi is not None and hi < lo:
            hi = None  # the fallback max over other taxa is below this taxon's open lower bound
        if lo is None or hi is None:
            residue.append(({"id": ",".join(cl for _, _, cl in rs), "taxon": tname, "trait": text(c["title"]), "value": [lo, hi], "page": "?"},
                            "open bound and no min/max anywhere for this character; set min/max in the design"))
            continue
        sid = "statement:" + uuid.uuid4().hex
        stmts.append({"id": sid, "taxon": t, "character": cid, "value": [lo, hi], "frequency": 1})
        prov.append({"statement": sid, "claims": [cl for _, _, cl in rs]})
        c["min"] = min(c.get("min", lo), lo)
        c["max"] = max(c.get("max", hi), hi)
    for (t, cid), by_state in cat_acc.items():
        for sid, lst in by_state.items():
            f = round(max(x for x, _ in lst), 4)
            st = "statement:" + uuid.uuid4().hex
            stmts.append({"id": st, "taxon": t, "character": cid, "value": sid, "frequency": f})
            prov.append({"statement": st, "claims": sorted({cl for _, cl in lst})})

    out = {"taxa": taxa_out, "characters": chars_out, "statements": stmts, "provenance": prov}
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.residue:
        lines = [f"# Residue: {len(residue)} claims not scored\n"]
        for cl, why in residue:
            lines.append(f"- `{cl.get('id', '?')}` {cl.get('taxon', '?')} p.{cl.get('page', '?')}: {cl.get('trait')} = {cl.get('value')}  ({why})")
        a.residue.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(stmts)} statements from {len(claims) - len(residue)} claims; {len(residue)} in residue -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
