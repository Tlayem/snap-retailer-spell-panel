#!/usr/bin/env python3
"""09_public_package.py — copy the publishable files into ../snap-retailer-spell-panel-public/.

Leaves out raw inputs (fetched by 01_fetch.py; hashes in PROVENANCE.txt), interim files,
and the private working documents (build spec, verification checklist, publish guide).
"""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT.parent / "snap-retailer-spell-panel-public"
PRIVATE = {"docs/BUILD_SPEC.md", "docs/VERIFY_CHECKLIST.md", "docs/PUBLISH_GUIDE.md", "docs/NEXT_STEPS.md"}
INCLUDE = ["README.md", "LICENSE", "LICENSE-DATA", "CITATION.cff", ".zenodo.json", ".gitignore", "AUTHORS.json",
           "code", "docs", "data/processed", "data/raw/PROVENANCE.txt"]

if DEST.exists():
    shutil.rmtree(DEST)
for item in INCLUDE:
    src = ROOT / item
    files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if rel in PRIVATE or "__pycache__" in rel:
            continue
        out = DEST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
n = sum(1 for p in DEST.rglob("*") if p.is_file())
print(f"{n} files in {DEST}")
for p in sorted(DEST.rglob("*")):
    if p.is_file():
        print(f"  {p.stat().st_size / 1e6:8.2f} MB  {p.relative_to(DEST)}")
