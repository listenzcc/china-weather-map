#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch China prefecture-level GeoJSON from DataV.GeoAtlas and build:
  - china-geo.json : FeatureCollection of all prefecture polygons (ECharts base map)
  - cities.json     : list of {name, adcode, lon, lat, province} for weather lookup
Uses only the standard library (urllib) so no pip install is required.
"""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "https://geo.datav.aliyun.com/areas_v3/bound/"
OUT_DIR = "."

# Provinces/municipalities/special regions that have no prefecture-level
# subdivisions worth splitting: keep them as a single map feature.
COLLAPSE = {110000, 120000, 310000, 500000, 710000, 810000, 820000}


def fetch_json(url, retries=4, timeout=30):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            time.sleep(1.5 + i)
    raise RuntimeError(f"fetch failed after retries: {url} ({last})")


def main():
    print("== fetch province list ==")
    prov = fetch_json(BASE + "100000_full.json")
    features = prov.get("features", [])
    print(f"provinces: {len(features)}")

    all_features = []   # for china-geo.json
    cities = []         # for weather lookup

    for pf in features:
        pname = pf["properties"].get("name", "")
        raw = pf["properties"].get("adcode")
        try:
            adcode = int(raw)
        except (TypeError, ValueError):
            # special feature (e.g. 南海诸岛 / 九段线 boundary) -> keep geometry
            # on the base map for compliance, but not a weather city.
            if pf.get("geometry"):
                all_features.append({
                    "type": "Feature",
                    "properties": {"name": pname or "南海诸岛",
                                   "adcode": str(raw), "province": pname or "南海诸岛"},
                    "geometry": pf["geometry"],
                })
            continue
        pcenter = pf["properties"].get("center")  # [lon, lat]
        if adcode in COLLAPSE:
            # single feature for the whole municipality / region
            geom = pf.get("geometry")
            if geom:
                all_features.append({
                    "type": "Feature",
                    "properties": {"name": pname, "adcode": adcode, "province": pname},
                    "geometry": geom,
                })
            if pcenter:
                cities.append({"name": pname, "adcode": adcode,
                               "lon": pcenter[0], "lat": pcenter[1], "province": pname})
            continue

        # fetch prefecture-level subdivisions
        try:
            sub = fetch_json(f"{BASE}{adcode}_full.json")
        except RuntimeError as e:
            print(f"  ! skip {pname} ({adcode}): {e}", file=sys.stderr)
            # fall back to province feature as one city
            if pf.get("geometry"):
                all_features.append({
                    "type": "Feature",
                    "properties": {"name": pname, "adcode": adcode, "province": pname},
                    "geometry": pf["geometry"],
                })
            if pcenter:
                cities.append({"name": pname, "adcode": adcode,
                               "lon": pcenter[0], "lat": pcenter[1], "province": pname})
            continue

        for sf in sub.get("features", []):
            props = sf.get("properties", {})
            name = props.get("name", "")
            center = props.get("center") or props.get("centroid")
            geom = sf.get("geometry")
            if not name or not geom:
                continue
            all_features.append({
                "type": "Feature",
                "properties": {"name": name, "adcode": int(props.get("adcode", 0)),
                               "province": pname},
                "geometry": geom,
            })
            if center:
                cities.append({"name": name, "adcode": int(props.get("adcode", 0)),
                               "lon": center[0], "lat": center[1], "province": pname})

    fc = {"type": "FeatureCollection", "features": all_features}
    with open(f"{OUT_DIR}/china-geo.json", "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    with open(f"{OUT_DIR}/cities.json", "w", encoding="utf-8") as f:
        json.dump(cities, f, ensure_ascii=False)

    print(f"china-geo.json features: {len(all_features)}")
    print(f"cities: {len(cities)}")
    # quick sanity: show a few
    print("sample:", cities[:3])


if __name__ == "__main__":
    main()
