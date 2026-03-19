import json
import sqlite3
from datetime import datetime, timezone
from collections import Counter

DB_PATH = "data/market_structure.db"
SYMBOL = "NQ"


def parse_dt(value: str) -> datetime:
    # stored ISO comes from python datetime.isoformat(). candles are ISO as well.
    # Some payloads may have Z; normalize.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def timeframe_seconds(tf: str) -> int | None:
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return mapping.get(tf)


def analyze_snapshot_candles(payload: dict) -> dict:
    candles = payload.get("candles") or []
    if not candles:
        return {"bars": 0}

    tf = payload.get("display_timeframe")
    tf_sec = timeframe_seconds(tf) if tf else None

    started = [parse_dt(c["started_at"]) for c in candles if c.get("started_at")]
    started.sort()

    gaps = []
    if tf_sec is not None:
        for a, b in zip(started, started[1:]):
            delta = (b - a).total_seconds()
            if delta > tf_sec * 1.5:
                gaps.append({
                    "from": a.isoformat(),
                    "to": b.isoformat(),
                    "delta_sec": int(delta),
                    "missing_bars_est": int(round(delta / tf_sec)) - 1,
                })

    closes = [c.get("close") for c in candles if c.get("close") is not None]
    close_range = (min(closes), max(closes)) if closes else (None, None)

    # detect outlier bars by median absolute deviation (rough)
    sorted_closes = sorted(closes)
    median = None
    mad = None
    outliers = []
    if sorted_closes:
        mid = len(sorted_closes) // 2
        median = sorted_closes[mid] if len(sorted_closes) % 2 else (sorted_closes[mid - 1] + sorted_closes[mid]) / 2
        abs_dev = [abs(x - median) for x in closes]
        abs_dev_sorted = sorted(abs_dev)
        mid2 = len(abs_dev_sorted) // 2
        mad = abs_dev_sorted[mid2] if len(abs_dev_sorted) % 2 else (abs_dev_sorted[mid2 - 1] + abs_dev_sorted[mid2]) / 2
        # avoid zero MAD
        thresh = (mad or 1e-9) * 12
        for c in candles:
            close = c.get("close")
            if close is None:
                continue
            if abs(close - median) > thresh:
                outliers.append({"started_at": c.get("started_at"), "close": close})

    return {
        "bars": len(candles),
        "timeframe": tf,
        "window_start": payload.get("window_start"),
        "window_end": payload.get("window_end"),
        "first": started[0].isoformat() if started else None,
        "last": started[-1].isoformat() if started else None,
        "gap_count": len(gaps),
        "largest_gap": max(gaps, key=lambda g: g["delta_sec"]) if gaps else None,
        "close_min": close_range[0],
        "close_max": close_range[1],
        "median_close": median,
        "mad_close": mad,
        "outlier_count": len(outliers),
        "outliers": outliers[:10],
    }


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    kinds = [r[0] for r in con.execute("select distinct ingestion_kind from ingestions order by 1").fetchall()]
    print("ingestion_kinds:")
    for k in kinds:
        print(" -", k)

    rows = con.execute(
        """
        select ingestion_id, stored_at, ingestion_kind, observed_payload_json
        from ingestions
        where instrument_symbol = ?
        order by stored_at desc
        limit 300
        """,
        (SYMBOL,),
    ).fetchall()

    counts = Counter([r["ingestion_kind"] for r in rows])
    print("\nlatest 300 ingestions by kind:")
    for k, v in counts.most_common():
        print(f" - {k}: {v}")

    # focus on latest replay snapshots
    snap_rows = [r for r in rows if r["ingestion_kind"] == "replay_workbench_snapshot"]
    print(f"\nreplay_workbench_snapshot rows inspected: {len(snap_rows)}")

    reports = []
    for r in snap_rows[:60]:
        payload = json.loads(r["observed_payload_json"])
        rep = analyze_snapshot_candles(payload)
        rep.update({"ingestion_id": r["ingestion_id"], "stored_at": r["stored_at"]})
        reports.append(rep)

    # print suspicious ones first
    suspicious = [
        rep
        for rep in reports
        if (rep.get("largest_gap") is not None and rep["largest_gap"]["delta_sec"] > 120)
        or (rep.get("outlier_count", 0) > 0)
    ]

    def score(rep: dict) -> tuple:
        lg = rep.get("largest_gap")
        return (
            -(lg["delta_sec"] if lg else 0),
            -rep.get("outlier_count", 0),
            rep.get("stored_at") or "",
        )

    suspicious.sort(key=score)

    print("\nSUSPICIOUS snapshots (gap>2min or outliers):", len(suspicious))
    for rep in suspicious[:20]:
        print("\n", rep["ingestion_id"], rep["stored_at"], "tf", rep.get("timeframe"), "bars", rep.get("bars"))
        print("  window", rep.get("window_start"), "->", rep.get("window_end"))
        if rep.get("largest_gap"):
            g = rep["largest_gap"]
            print("  largest_gap", g["delta_sec"], "sec missing~", g["missing_bars_est"], "between", g["from"], "and", g["to"])
        if rep.get("outlier_count"):
            print("  outliers", rep.get("outlier_count"), "median", rep.get("median_close"), "mad", rep.get("mad_close"))
            for o in rep.get("outliers")[:5]:
                print("    -", o)

    # also show latest snapshot summary
    if reports:
        latest = reports[0]
        print("\nLATEST snapshot summary:")
        print(json.dumps({k: latest[k] for k in ["ingestion_id","stored_at","timeframe","bars","window_start","window_end","first","last","gap_count","largest_gap","close_min","close_max"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
