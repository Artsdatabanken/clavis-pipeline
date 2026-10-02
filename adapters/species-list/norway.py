#!/usr/bin/env python3
"""Species list for a Norwegian taxon: NorTaxa subtree (ExistsInNorway) merged
with Fremmedartslista 2023 doorknockers (dorstokkarter) whose genus falls in
the subtree. Generalized from Gnagere/norway_rodent_candidates.py.

Usage: norway.py <taxon-name> [out.csv]

Name resolution requires an EXACT accepted-name match in NorTaxa search.
Anything fuzzier is listed and the script exits 1 — string-similarity
suggestions must never be auto-accepted (they can silently swap species).
"""
import csv, io, json, re, sys, urllib.parse, urllib.request

def get(url):
    with urllib.request.urlopen(url) as r:
        return r.read()

def plain(name):
    return re.sub(r"\s*\([^)]*\)", "", name)  # strip subgenus

taxon = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else f"{taxon.lower()}_norway.csv"

# 1. Resolve name -> scientificNameId (exact accepted match only)
hits = json.loads(get("https://nortaxa.artsdatabanken.no/api/v1/TaxonName/Search?search="
                      + urllib.parse.quote(taxon)))
exact = [h["acceptedScientificName"] for h in hits
         if h["acceptedScientificName"]["name"].lower() == taxon.lower()]
if len(exact) != 1:
    print(f"No unique exact match for {taxon!r}. Candidates:", file=sys.stderr)
    for h in hits:
        a = h["acceptedScientificName"]
        print(f"  {a['name']} ({a['rank']}, nameId {a['nameId']})", file=sys.stderr)
    sys.exit(1)
name_id, rank = exact[0]["nameId"], exact[0]["rank"]
print(f"{taxon}: nameId {name_id} ({rank})", file=sys.stderr)

# 2. Subtree export: accepted species with ExistsInNorway, plus genera
rows = csv.DictReader(io.StringIO(get(
    "https://nortaxa.artsdatabanken.no/api/v1/DataTransfer/Export"
    f"?scientificNameId={name_id}&includeSynonyms=false"
    "&includeVernacularNames=false&exportType=Csv").decode("utf-8-sig")),
    delimiter=";")
in_norway, genera = set(), set()
for r in rows:
    if r["Rank"] == "Genus":
        genera.add(r["PresentationName"])
    if (r["Rank"] == "Species" and r["TaxonomicStatus"] == "Accepted"
            and r["ExistsInNorway"] == "True"):
        in_norway.add(plain(r["PresentationName"]))

# 3. Doorknockers from Fremmedartslista 2023 (all expert groups; the genus
#    test decides membership). Follow OData paging.
doorknockers, url = {}, ("https://lister.artsdatabanken.no/odata/v1/alienspeciesassessment2023?"
    + urllib.parse.quote("$select=scientificName,category,alienSpeciesCategory"
                         "&$filter=alienSpeciesCategory eq 'DoorKnocker'", safe="=&$'"))
while url:
    page = json.loads(get(url))
    for a in page["value"]:
        name = plain(re.sub("<[^>]+>", "", a["scientificName"]["scientificNameFormatted"]))
        if name.split()[0] in genera:
            doorknockers[name] = a["category"]
    url = page.get("@odata.nextLink")

with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["scientificName", "inNorway", "doorknockerRisk"])
    for n in sorted(in_norway | set(doorknockers)):
        w.writerow([n, n in in_norway, doorknockers.get(n, "")])
print(f"{out}: {len(in_norway | set(doorknockers))} species "
      f"({len(in_norway)} in Norway, {len(doorknockers)} doorknockers)", file=sys.stderr)
