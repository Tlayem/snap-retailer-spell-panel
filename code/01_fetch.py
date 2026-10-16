#!/usr/bin/env python3
"""01_fetch.py — obtain the two raw inputs, verify them, log provenance, extract.

Inputs (both U.S. government works, public domain):
  1. USDA FNS, SNAP Retailer Locator historical data 2005-2025
     (current as of 31 Dec 2025; landing page updated 19 Feb 2026)
  2. U.S. Census Bureau, 2020 cartographic boundary file, census tracts, nation, 1:500,000

The script tries each download. USDA and Census hosts often refuse automated
clients; if a download fails, save the file by hand from the landing page into
data/raw/ under the name printed and re-run. The script then checks the SHA-256
against the vintage this release was built on and records it in
data/raw/PROVENANCE.txt.

For the tract file, the unzipped shapefile parts (.shp .shx .dbf .prj .cpg) in
data/raw/cb_2020_us_tract_500k/ are accepted in place of the zip.

Usage:  python code/01_fetch.py
"""
import datetime
import hashlib
import pathlib
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EXT = RAW / "extracted"
LOG = RAW / "PROVENANCE.txt"

SOURCES = [
    dict(
        name="snap-retailer-locator-data2005-2025.zip",
        url="https://www.fns.usda.gov/sites/default/files/resource-files/snap-retailer-locator-data2005-2025.zip",
        landing="https://www.fns.usda.gov/snap/retailer-locator/data",
        expect_sha="872a6f814a63514a1f1b0c4517a90309a9fbb01d97d6e4dbb1e8b20421c08cce",
        unzip_to=EXT,
    ),
    dict(
        name="cb_2020_us_tract_500k.zip",
        url="https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_tract_500k.zip",
        landing="https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.2020.html",
        expect_sha="2375fd892078592cb6ede13ec81821923ce575f6d801b00c236bfe1521901394",
        unzip_to=RAW / "cb_2020_us_tract_500k",
        parts=[".shp", ".shx", ".dbf", ".prj", ".cpg"],
    ),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log_line(fname, path, url, note):
    line = " | ".join([datetime.date.today().isoformat(), fname, f"{path.stat().st_size} bytes",
                       f"sha256:{sha256(path)}", url, note])
    existing = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    if f"{fname} |" not in existing or f"sha256:{sha256(path)}" not in existing:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(line)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for s in SOURCES:
        dest = RAW / s["name"]
        parts_dir = s["unzip_to"]
        stem = s["name"].removesuffix(".zip")
        have_parts = "parts" in s and all((parts_dir / f"{stem}{p}").exists() for p in s["parts"])
        how = "supplied by the author (browser download)"
        if not dest.exists() and not have_parts:
            try:
                req = urllib.request.Request(s["url"], headers={"User-Agent": "Mozilla/5.0 (research replication)"})
                with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
                    f.write(r.read())
                how = "downloaded by 01_fetch.py"
            except Exception as e:  # noqa: BLE001
                raise SystemExit(f"Could not download {s['name']} ({e}).\n"
                                 f"Download it by hand from {s['landing']} and save it as {dest}, then re-run.")
        if dest.exists():
            digest = sha256(dest)
            if s["expect_sha"]:
                how += "; matches" if digest == s["expect_sha"] else "; DIFFERS FROM"
                how += " the vintage this release was built on"
            log_line(s["name"], dest, s["url"], how)
            with zipfile.ZipFile(dest) as z:
                z.extractall(parts_dir)
        else:  # unzipped parts supplied
            for p in s["parts"]:
                f = parts_dir / f"{stem}{p}"
                log_line(f.name, f, s["url"], how + "; unzipped part of " + s["name"])


if __name__ == "__main__":
    main()
