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
    {"key": "tail_flat", "title": {"nb": "Flat hale"}, "type": "exclusive", "absent": "no",
     "states": [{"key": "yes", "title": {"nb": "ja"}, "values": ["flat", "flattrykt"]},
                {"key": "no",  "title": {"nb": "nei"}, "values": ["rund", "ikke flat"]}],
     "traits": ["haleform", "flat hale"]},
    ...
  ],
  "same_as_excludes": ["distribution", "litter"],
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
  * DIAGNOSTIC traits imply absence elsewhere: when a character in the design
    names an `absent` state (its key), and a claim scored on it is
    `diagnostic: true` (the source presents the trait as what distinguishes
    the taxon), every other design taxon with no claim on that character gets
    the absent state, provenance = the diagnostic claim. A trait that is
    diagnostic for one species is, by the source's own logic, lacking in the
    others it describes. Exclusive characters only.
  * SAME-AS: a claim with `same_as: "<scientific name>"` (the source says the
    taxon cannot be told from that one) copies, for every character the taxon
    has no statement on, the other taxon's statements, provenance = the
    same-as claim plus the copied statements' claims. Characters listed in the
    design's `same_as_excludes` (location, counts of young) are not copied.

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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harvest-claims" / "scripts"))
from claims_vs_key import unit_factor  # mm/cm/m and g/kg converted to the character unit

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
    diagnostic_hits = defaultdict(list)   # char id -> [claim id] for diagnostic claims scored on it
    same_as = defaultdict(list)           # taxon id -> [(target taxon id, claim id)]
    absent_state = {}
    for c in design["characters"]:
        if c.get("absent") and c.get("type", "exclusive") == "exclusive":
            for s_ in c["states"]:
                if s_["key"] == c["absent"]:
                    node = next(x for x in chars_out if x["id"] == c["_id"])
                    absent_state[c["_id"]] = next(sn["id"] for sn in node["states"] if sn["title"] == s_["title"])
    excludes = {k for k in design.get("same_as_excludes", [])}
    exclude_ids = {c["_id"] for c in design["characters"] if c["key"] in excludes}
    numeric_acc = defaultdict(lambda: defaultdict(list))  # (taxon id, char id) -> [(lo, hi, claim id)]
    cat_acc = defaultdict(lambda: defaultdict(list))      # (taxon id, char id) -> state id -> [(freq, claim id)]
    for cl in claims:
        if cl.get("observable") is False:
            continue
        t = tid.get(norm(cl["taxon"]))
        if not t:
            residue.append((cl, "taxon not in design"))
            continue
        if cl.get("same_as"):
            target = tid.get(norm(cl["same_as"]))
            if target and target != t:
                same_as[t].append((target, cl["id"]))
            else:
                residue.append((cl, "same_as names a taxon not in the design"))
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
                f = unit_factor(cl.get("unit"), c.get("unit"))
                numeric_acc[(t, c["_id"])]["r"].append((None if vn[0] is None else vn[0] * f,
                                                        None if vn[1] is None else vn[1] * f, cl["id"]))
                placed = True
            else:
                v = norm(cl["value"])
                words = f" {v} "
                # an exact match on the whole value wins: "ikke hareskår" must not
                # also score "hareskår", "grålig hvit" not also "hvit"
                hit = [(sid, vals) for sid, vals in state_index[c["key"]] if v in vals]
                if not hit:
                    hit = [(sid, vals) for sid, vals in state_index[c["key"]] if any(f" {x} " in words for x in vals if x)]
                if not hit:
                    continue
                q = cl.get("qualifier", "unspecified")
                f0 = ft.get(q, 1.0)
                f1 = ft.get("_secondary", {}).get(q, 1.0) if q in ft.get("_secondary", {}) else ft["_secondary"].get("or", 1.0)
                for k, (sid, _) in enumerate(hit):
                    cat_acc[(t, c["_id"])][sid].append((f0 if k == 0 or c.get("type") == "non-exclusive" else f1, cl["id"]))
                if cl.get("diagnostic") and absent_state.get(c["_id"]):
                    diagnostic_hits[c["_id"]].append(cl["id"])
                placed = True
        if not placed:
            residue.append((cl, "character found, no state matches the value (add a state or a synonym, or skip with a reason)"))

    # numerical: union of each taxon's ranges; an open side closes at the
    # character's min/max from the design, else at the extreme over all taxa
    # with a known bound, else the claim goes to the residue
    design_min = {x["id"]: x.get("min") for x in chars_out if x["type"] == "numerical"}
    design_max = {x["id"]: x.get("max") for x in chars_out if x["type"] == "numerical"}
    known_lo, known_hi = defaultdict(list), defaultdict(list)
    for (t, cid), d in numeric_acc.items():
        for lo, hi, _ in d["r"]:
            if lo is not None: known_lo[cid].append(lo)
            if hi is not None: known_hi[cid].append(hi)
    for (t, cid), d in numeric_acc.items():
        rs = d["r"]
        c = next(x for x in chars_out if x["id"] == cid)
        # close each claim's open side at the design min/max, else at the extreme
        # over ALL taxa (not the running min/max of statements written so far),
        # then take the union over the taxon's claims (an open bound must not
        # vanish because another claim of the same taxon has a closed one)
        fb_lo = design_min[cid] if design_min.get(cid) is not None else (min(known_lo[cid]) if known_lo[cid] else None)
        fb_hi = design_max[cid] if design_max.get(cid) is not None else (max(known_hi[cid]) if known_hi[cid] else None)
        closed = [(fb_lo if l is None else l, fb_hi if h is None else h) for l, h, _ in rs]
        lo = None if any(l is None for l, _ in closed) else min(l for l, _ in closed)
        hi = None if any(h is None for _, h in closed) else max(h for _, h in closed)
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
    # implied absence: a diagnostic trait is lacking in every other taxon the
    # source describes (that is what makes it diagnostic)
    implied = 0
    for cid, claim_ids in diagnostic_hits.items():
        for t in tid.values():
            if (t, cid) not in cat_acc:
                cat_acc[(t, cid)][absent_state[cid]].append((1.0, claim_ids[0]))
                implied += 1
    for (t, cid), by_state in cat_acc.items():
        for sid, lst in by_state.items():
            f = round(max(x for x, _ in lst), 4)
            st = "statement:" + uuid.uuid4().hex
            stmts.append({"id": st, "taxon": t, "character": cid, "value": sid, "frequency": f})
            prov.append({"statement": st, "claims": sorted({cl for _, cl in lst})})

    # same-as: copy the look-alike's statements where this taxon has none
    copied = 0
    by_tc = defaultdict(list)
    for st_, pv in zip(stmts, prov):
        by_tc[(st_["taxon"], st_["character"])].append((st_, pv))
    for t, targets in same_as.items():
        for target, claim_id in targets:
            for (tt, cid), lst in list(by_tc.items()):
                if tt != target or cid in exclude_ids or (t, cid) in by_tc:
                    continue
                for st_, pv in lst:
                    nid = "statement:" + uuid.uuid4().hex
                    new = dict(st_, id=nid, taxon=t)
                    stmts.append(new); prov.append({"statement": nid, "claims": [claim_id] + pv["claims"], "note": "copied: source says the taxon cannot be told from " + next(x["scientificName"] for x in taxa_out if x["id"] == target)})
                    by_tc[(t, cid)].append((new, prov[-1])); copied += 1
    out = {"taxa": taxa_out, "characters": chars_out, "statements": stmts, "provenance": prov}
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.residue:
        lines = [f"# Residue: {len(residue)} claims not scored\n"]
        for cl, why in residue:
            lines.append(f"- `{cl.get('id', '?')}` {cl.get('taxon', '?')} p.{cl.get('page', '?')}: {cl.get('trait')} = {cl.get('value')}  ({why})")
        a.residue.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(stmts)} statements from {len(claims) - len(residue)} claims ({implied} implied absent from diagnostic traits, {copied} copied from look-alikes); {len(residue)} in residue -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
