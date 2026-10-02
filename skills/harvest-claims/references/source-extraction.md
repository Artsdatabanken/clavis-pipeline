# Reading the source: text extraction and figure labels

Part of the `harvest-claims` skill: background on text extraction and why figure labels need vision. The scripts in `scripts/` automate the steps described here.

### Step 0: Extract the bounded text once, up front

**Do this before anything else.** Reading PDFs/PNGs via vision is expensive — and re-reading the same pages across iterations (to check a couplet, look up a species description, verify a figure number) compounds the cost fast. Extract the bounded text **once** into a working file in a scratch folder (`work/` next to the source), then do all subsequent prose reads from that file with the Read tool.

For a PDF with a text layer, the cheap path is:

```
pdftotext -f <first_page> -l <last_page> -layout <source.pdf> work/<group>_text.txt
```

`pdftotext` is part of poppler. Where it is not installed (typical on Windows), extract the same pages with `pypdf` instead: `python -c "import pypdf,sys; r=pypdf.PdfReader(sys.argv[1]); print('\n\f'.join(p.extract_text() for p in r.pages[int(sys.argv[2])-1:int(sys.argv[3])]))" <source.pdf> <first_page> <last_page> > work/<group>_text.txt`. Either way, write to a `work/` folder next to the source, not into the source folder itself.

For a PDF without a text layer (scans), fall back to Tesseract or a similar OCR. For a Word doc, `pandoc -t plain` or `docx2txt`. For a folder of images, OCR each in the bounded range.

Then verify the extraction covers the right pages by reading the first and last 20 lines of the working file — check the start matches the target group's heading and the end stops before the next group's heading. **If the bounded range cuts off mid-key (e.g. some species descriptions sit on a later page outside the user's range), extend the extraction to capture them — the printed page bounds the user gave may not be airtight.** Note this in the decisions doc.

After this step:
- Use the Read tool on the working text file for all prose lookups.
- Reserve PDF rendering + vision for the figure-plate pass (next section) and ambiguous lines only.

Always read every page of the working file once through before designing characters. Do not infer contents from headings or numbering alone. Watch for the section heading change at the end of the target group — section bleed is a common error.

When transcribing, capture any **identifier or catalogue number** in the source margin (e.g. species number, track ID, type designation). These numbers don't go into Clavis but help cross-reference figures or images and verify completeness.

### Vision-read figure labels

OCR/text-layer extraction (pdftotext, Tesseract) handles flowing prose well but tends to fail on **floating labels around illustrations** — the arrowed captions, comparison plates, and feature pointers that field guides routinely use. Labels often carry the most concentrated diagnostic information per square cm of any source content (e.g. "smal vingebasis", "naken lys nebbrot", "kileformet"), and OCR either drops them, scrambles their order, or merges them into adjacent species' text.

**Always vision-read at least:**
- Every comparison plate (one figure showing multiple species side-by-side with arrows).
- Every species illustration with three or more arrowed labels.
- Any figure where labels point inside the bird/animal/specimen rather than sitting in margin space.

For long sources, this is in addition to the OCR pass — don't replace OCR with vision, supplement it. After vision-reading a figure, cross-check that every diagnostic label is reflected in some character/state pair, and flag any that aren't.

When the source language uses non-Latin scripts (Mandarin, Cyrillic, Arabic, Devanagari) or heavily diacriticised text, vision is often more reliable than OCR even for body text — OCR error rates climb sharply outside Latin-1.
