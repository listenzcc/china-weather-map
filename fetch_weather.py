#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch 5 years (2021-2025) of daily mean temperature & precipitation for every
Chinese prefecture city from Open-Meteo archive API, aggregate by calendar day
(ignore Feb 29), and emit data.json with per-city per-day climate means.

Notes:
  - Open-Meteo accepts comma-separated lat/lon in ONE request, so we batch cities
    (BATCH per request) -> only a handful of HTTP calls total.
  - The free API has an HOURLY request limit. We probe until it clears, then fetch,
    so a long cooldown does not abort the run.
  - Resumable: reads existing data.json and only fetches cities still missing.
Only the standard library is used (urllib).
"""
import json
import time
import datetime
import urllib.request
import urllib.error

API = "https://archive-api.open-meteo.com/v1/archive"
START = "2021-01-01"
END = "2025-12-31"
BATCH = 40            # cities per request (minimize total request count)
SPACING = 540         # ~9 min between batches -> stays under hourly request quota
BACKOFF_429 = 20      # seconds to wait on a transient 429
HOURLY_WAIT = 3600    # sleep a full hour when the hourly quota wall is hit
PROBE = "https://archive-api.open-meteo.com/v1/archive?latitude=39.9&longitude=116.4" \
        "&start_date=2024-01-01&end_date=2024-01-02&daily=temperature_2m_mean"


def doy(mm, dd):
    return (datetime.date(2001, mm, dd) - datetime.date(2001, 1, 1)).days + 1


def probe_ok():
    try:
        req = urllib.request.Request(PROBE, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code != 429
    except Exception:
        return False


def wait_until_ok(max_wait=6000):
    if probe_ok():
        return
    waited = 0
    print("hourly limit active; waiting for it to clear ...", flush=True)
    while not probe_ok():
        time.sleep(300)
        waited += 300
        if waited >= max_wait:
            print("gave up waiting after", waited, "s", flush=True)
            return
    print(f"rate limit cleared after ~{waited}s", flush=True)


def fetch_batch(batch):
    lats = ",".join(f"{c['lat']:.4f}" for c in batch)
    lons = ",".join(f"{c['lon']:.4f}" for c in batch)
    url = (f"{API}?latitude={lats}&longitude={lons}"
           f"&start_date={START}&end_date={END}"
           f"&daily=temperature_2m_mean,precipitation_sum&timezone=Asia%2FShanghai")
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                obj = json.loads(r.read().decode("utf-8"))
            results = obj if isinstance(obj, list) else [obj]
            out = []
            for res in results:
                daily = res.get("daily", {})
                times = daily.get("time", [])
                tarr = daily.get("temperature_2m_mean", [])
                parr = daily.get("precipitation_sum", [])
                buckets = {d: [] for d in range(1, 366)}
                for ds, t, p in zip(times, tarr, parr):
                    y, m, d = (int(x) for x in ds.split("-"))
                    if m == 2 and d == 29:
                        continue
                    buckets[doy(m, d)].append((t, p))
                T = [None] * 365
                P = [None] * 365
                for k, vals in buckets.items():
                    if not vals:
                        continue
                    ts = [v[0] for v in vals if v[0] is not None]
                    ps = [v[1] for v in vals if v[1] is not None]
                    T[k - 1] = round(sum(ts) / len(ts), 1) if ts else None
                    P[k - 1] = round(sum(ps) / len(ps), 1) if ps else None
                out.append((T, P))
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(BACKOFF_429 + attempt * 5)
                continue
            time.sleep(3)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(3 + attempt)
    print(f"  ! FAILED batch of {len(batch)}", flush=True)
    return None


def fetch_batch_with_retry(batch, max_retry=3):
    for attempt in range(max_retry):
        r = fetch_batch(batch)
        if r is not None:
            return r
        print(f"  batch hit limit, sleep {HOURLY_WAIT}s (retry {attempt+1}/{max_retry}) ...", flush=True)
        time.sleep(HOURLY_WAIT)
    return None


def main():
    with open("cities.json", encoding="utf-8") as f:
        cities = json.load(f)

    existing = {}
    try:
        with open("data.json", encoding="utf-8") as f:
            prev = json.load(f)
        for c in prev.get("cities", []):
            if any(v is not None for v in c.get("T", [])):
                existing[c["adcode"]] = c
        print(f"resume: {len(existing)} cities already have data", flush=True)
    except FileNotFoundError:
        pass

    out = {c["adcode"]: c for c in existing.values()}
    todo = [c for c in cities if c["adcode"] not in out]
    print(f"{len(todo)} cities still need fetching", flush=True)
    if not todo:
        _write(out)
        print("nothing to do")
        return

    wait_until_ok()
    i = 0
    while i < len(todo):
        batch = todo[i:i + BATCH]
        res = fetch_batch_with_retry(batch)
        if res is None:
            i += BATCH
            continue
        for c, (T, P) in zip(batch, res):
            out[c["adcode"]] = {
                "name": c["name"], "adcode": c["adcode"],
                "lon": c["lon"], "lat": c["lat"], "province": c["province"],
                "T": T, "P": P,
            }
        i += BATCH
        if i % (BATCH * 2) == 0 or i >= len(todo):
            _write(out)
            print(f"  progress {i}/{len(todo)}", flush=True)
        time.sleep(SPACING)

    missing = [c for c in cities if c["adcode"] not in out]
    if missing:
        print(f"retry {len(missing)} missing cities ...", flush=True)
        for c in missing:
            res = fetch_batch([c])
            if res:
                T, P = res[0]
                out[c["adcode"]] = {**c, "T": T, "P": P}
            time.sleep(SPACING)

    _write(out)
    out_cities = [out.get(c["adcode"], c) for c in cities]
    ok = sum(1 for c in out_cities if any(v is not None for v in c.get("T", [])))
    print(f"data.json written. cities={len(out_cities)} with data={ok}")
    for name in ("哈尔滨市", "海口市", "北京市", "广州市"):
        c = next((x for x in out_cities if x["name"] == name), None)
        if c:
            print(f"  QC {name}: Jan1 T={c['T'][0]} P={c['P'][0]}; Jul1 T={c['T'][181]} P={c['P'][181]}")


def _write(out_map):
    data = {
        "meta": {
            "years": [2021, 2022, 2023, 2024, 2025],
            "source": "Open-Meteo Historical Weather API (archive)",
            "generated": datetime.date.today().isoformat(),
            "aggregation": "per calendar day, 5-year mean (Feb 29 excluded)",
            "vars": {"T": "temperature_2m_mean (C)", "P": "precipitation_sum (mm/day)"},
        },
        "days": 365,
        "cities": list(out_map.values()),
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
