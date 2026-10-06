"""
供應鏈地圖的每日資料：海外龍頭與台股相關公司的漲跌、走勢，加上台股的法人 5 日買賣超。

- 價格：yfinance 一次批次下載（美股、日股 .T、韓股 .KS、台股 .TW／.TWO）
- 法人：picks.py 存的 data/flows/latest.json（證交所三大法人，只涵蓋上市公司）
- 關係：supply_map.py

輸出 data/supply/latest.json，build.py 讀取產生 /supply/ 頁面。
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from supply_map import LEADERS, TW_MAP

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "supply" / "latest.json"
FLOWS = ROOT / "data" / "flows" / "latest.json"
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"


def tw_listing() -> dict[str, str]:
    """代號 → 上市／上櫃，決定 yfinance 用 .TW 還是 .TWO。"""
    out = {}
    try:
        for r in requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers={"User-Agent": UA}, timeout=30).json():
            out[r["Code"]] = "上市"
        for r in requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers={"User-Agent": UA}, timeout=30).json():
            out.setdefault(r["SecuritiesCompanyCode"], "上櫃")
    except (requests.RequestException, ValueError) as exc:
        print(f"⚠️ 上市櫃清單讀取失敗，一律當上市：{exc}", file=sys.stderr)
    return out


def series_stats(df) -> dict | None:
    c = df["Close"].dropna()
    if len(c) < 6:
        return None
    return {
        "price": round(float(c.iloc[-1]), 2),
        "date": c.index[-1].date().isoformat(),
        "chg_1d": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
        "chg_5d": round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2),
        "spark": [round(float(x), 2) for x in c.tail(20)],
    }


def main() -> int:
    import yfinance as yf

    listing = tw_listing()
    tw_ticker = {code: f"{code}.TWO" if listing.get(code) == "上櫃" else f"{code}.TW" for code in TW_MAP}
    tickers = [v[2] for v in LEADERS.values()] + list(tw_ticker.values())
    data = yf.download(tickers, period="3mo", progress=False, auto_adjust=True, group_by="ticker", threads=True)

    def stats(t):
        try:
            return series_stats(data[t])
        except KeyError:
            return None

    flows = json.loads(FLOWS.read_text(encoding="utf-8")) if FLOWS.exists() else {"codes": {}}
    leaders = []
    for code, (name, market, yft, industry) in LEADERS.items():
        st = stats(yft)
        if st:
            leaders.append({"code": code, "name": name, "market": market, "industry": industry, **st})
        else:
            print(f"⚠️ {name}（{yft}）沒有報價", file=sys.stderr)
    tw = []
    for code, s in TW_MAP.items():
        st = stats(tw_ticker[code])
        if not st:
            print(f"⚠️ {s['name']}（{tw_ticker[code]}）沒有報價", file=sys.stderr)
            continue
        f = flows["codes"].get(code)
        tw.append({"code": code, "name": s["name"], "market": listing.get(code, "上市"), **st,
                   "flows": f, "links": {ld: list(v) for ld, v in s["links"].items()}})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "flows_date": flows.get("date"), "leaders": leaders, "tw": tw,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 供應鏈地圖：{len(leaders)} 家龍頭、{len(tw)} 家台股")
    return 0


if __name__ == "__main__":
    sys.exit(main())
