"""
大佬持股追蹤：SEC 13F 申報（美國管理資產超過 1 億美元的機構，每季申報美股持股，最晚季末後 45 天）。

為什麼不用 X／社群貼文：X 禁止爬蟲、官方 API 付費；而且「提到」不等於「買了」。13F 是有法律效力的官方申報，
每一筆都能連回 SEC 原始文件，符合本站「沒有出處就不放」的原則。

- 來源：data.sec.gov submissions JSON → 最新兩份 13F-HR → 申報資料夾裡的持股明細 XML（information table）
- CUSIP → 股票代號：OpenFIGI（免費、不需金鑰），對照表存在 data/whales/cusip.json
- 已下載的申報存在 data/whales/filings/，之後每天只檢查有沒有新申報，不會重抓
- SEC 要求程式讀取時 User-Agent 附聯絡 email；這裡用 GitHub 提供的匿名轉信地址，不用站長私人信箱

輸出 data/whales/latest.json，build.py 產生 /whales/、供應鏈頁區塊、四位投資人頁的真實持股。
大佬名單：站長之後會再提供更新，改 MANAGERS 就好（CIK 可在 sec.gov/edgar/search 查）。
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DIR = ROOT / "data" / "whales"
FILINGS = DIR / "filings"
CUSIP = DIR / "cusip.json"
OUT = DIR / "latest.json"
TAIPEI = timezone(timedelta(hours=8))
SEC_UA = os.environ.get("SEC_USER_AGENT") or "craig-finance-hub craigshih@users.noreply.github.com"

# (代號, 人物, 機構, CIK, 說明, 對應本站四位投資人的 id)
MANAGERS = [
    ("buffett", "巴菲特", "Berkshire Hathaway", 1067983, "波克夏海瑟威", "buffett"),
    ("duan", "段永平", "H&H International Investment", 1759760, "段永平的美國投資公司", "duan"),
    ("lilu", "李錄", "Himalaya Capital Management", 1709323, "喜馬拉雅資本", "lilu"),
    ("munger", "芒格", "Daily Journal Corp", 783412, "芒格生前長年擔任董事長的公司，持股多在他任內建立", "munger"),
    ("ackman", "Bill Ackman", "Pershing Square Capital Management", 1336528, "潘興廣場，集中持股的激進投資人", None),
    ("druck", "Stanley Druckenmiller", "Duquesne Family Office", 1536411, "索羅斯前操盤手的家族辦公室", None),
    ("tepper", "David Tepper", "Appaloosa", 1656456, "以抄底聞名的避險基金", None),
    ("wood", "Cathie Wood", "ARK Investment Management", 1697748, "方舟投資，專注破壞式創新", None),
    ("burry", "Michael Burry", "Scion Asset Management", 1649339, "《大賣空》主角", None),
    ("gates", "比爾蓋茲", "Bill & Melinda Gates Foundation Trust", 1166559, "蓋茲基金會信託", None),
]
CHANGE_TOLERANCE = 0.05  # 股數變動 5% 以內算「持平」


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


class SecBlocked(Exception):
    pass


def sec_get(url: str):
    for attempt in range(2):
        r = requests.get(url, headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate"}, timeout=40)
        if r.status_code == 200:
            time.sleep(0.25)  # SEC 上限每秒 10 次，這裡遠低於
            return r
        if r.status_code == 429 and attempt == 0:
            time.sleep(5)
            continue
        if r.status_code in (403, 429):
            # 被擋就整批停下，不要拖慢建站（通常是 User-Agent 的聯絡資訊不被接受）
            raise SecBlocked(f"SEC 回 {r.status_code}：{url}")
        r.raise_for_status()
    raise SecBlocked(f"SEC 一直拒絕：{url}")


def latest_13f(cik: int, n: int = 2) -> list[dict]:
    d = sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    r = d["filings"]["recent"]
    out, periods = [], set()
    for i, form in enumerate(r["form"]):
        if form != "13F-HR" or r["reportDate"][i] in periods:
            continue
        periods.add(r["reportDate"][i])
        out.append({"accession": r["accessionNumber"][i], "filed": r["filingDate"][i], "period": r["reportDate"][i]})
        if len(out) == n:
            break
    return [{"sec_name": d.get("name"), **f} for f in out]


def holdings_of(cik: int, accession: str) -> list[dict]:
    cache = FILINGS / f"{cik}_{accession}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    items = sec_get(f"{folder}/index.json").json()["directory"]["item"]
    xmls = [i["name"] for i in items if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower()]
    rows = []
    for name in xmls:
        root = ET.fromstring(sec_get(f"{folder}/{name}").content)
        if not root.tag.lower().endswith("informationtable"):
            continue
        for it in root:
            g = {c.tag.split("}")[-1]: c for c in it.iter()}
            if "cusip" not in g:
                continue
            rows.append({
                "cusip": g["cusip"].text.strip().upper(), "name": (g["nameOfIssuer"].text or "").strip(),
                "cls": (g.get("titleOfClass").text or "").strip() if g.get("titleOfClass") is not None else "",
                "value": float(g["value"].text), "shares": float(g["sshPrnamt"].text),
                "put_call": (g["putCall"].text or "").strip() if g.get("putCall") is not None else "",
            })
    FILINGS.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """同一檔（CUSIP）合併；選擇權另外標記，不算進持股。"""
    out: dict[str, dict] = {}
    for r in rows:
        key = r["cusip"] + (f':{r["put_call"].upper()}' if r["put_call"] else "")
        a = out.setdefault(key, {"cusip": r["cusip"], "name": r["name"], "value": 0.0, "shares": 0.0, "option": r["put_call"].upper() or None})
        a["value"] += r["value"]
        a["shares"] += r["shares"]
    return out


def map_cusips(cusips: set[str]) -> dict:
    mapping = json.loads(CUSIP.read_text(encoding="utf-8")) if CUSIP.exists() else {}
    todo = sorted(c for c in cusips if c not in mapping)
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        try:
            r = requests.post("https://api.openfigi.com/v3/mapping", timeout=30,
                              json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch])
            if r.status_code == 429:
                time.sleep(30)
                r = requests.post("https://api.openfigi.com/v3/mapping", timeout=30,
                                  json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch])
            r.raise_for_status()
            for c, res in zip(batch, r.json()):
                d = (res.get("data") or [{}])[0]
                mapping[c] = {"ticker": d.get("ticker"), "figi_name": d.get("name"), "type": d.get("securityType2")}
        except (requests.RequestException, ValueError) as exc:
            log(f"⚠️ OpenFIGI 失敗（{exc}），這批之後再補")
        time.sleep(2.6)  # 沒有金鑰：每分鐘 25 次
    DIR.mkdir(parents=True, exist_ok=True)
    CUSIP.write_text(json.dumps(mapping, ensure_ascii=False, indent=0), encoding="utf-8")
    return mapping


def compare(now: dict, prev: dict | None) -> tuple[list[dict], list[dict]]:
    total = sum(h["value"] for h in now.values() if not h["option"]) or 1
    rows = []
    for key, h in now.items():
        p = (prev or {}).get(key)
        if prev is None:
            change, pct = None, None
        elif not p:
            change, pct = "新買進", None
        else:
            pct = (h["shares"] / p["shares"] - 1) if p["shares"] else None
            change = "加碼" if pct and pct > CHANGE_TOLERANCE else "減碼" if pct and pct < -CHANGE_TOLERANCE else "持平"
        rows.append({**h, "weight": h["value"] / total * 100 if not h["option"] else None, "change": change,
                     "chg_pct": round(pct * 100, 1) if pct is not None else None})
    exits = [{**p, "change": "出清"} for key, p in (prev or {}).items() if key not in now and not p["option"]]
    rows.sort(key=lambda r: (r["option"] is not None, -r["value"]))
    exits.sort(key=lambda r: -r["value"])
    return rows, exits


def main() -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    managers, cusips = [], set()
    for mid, person, fund, cik, note, inv in MANAGERS:
        try:
            filings = latest_13f(cik)
            if not filings:
                log(f"⚠️ {person}（{fund}）沒有 13F")
                continue
            cur = aggregate(holdings_of(cik, filings[0]["accession"]))
            prev = aggregate(holdings_of(cik, filings[1]["accession"])) if len(filings) > 1 else None
        except SecBlocked as exc:
            log(f"❌ {exc}；這次先跳過，沿用上一份資料")
            return 0
        except Exception as exc:  # 單一大佬失敗不影響其他人
            log(f"⚠️ {person}（{fund}）讀取失敗：{exc}")
            continue
        rows, exits = compare(cur, prev)
        cusips |= {r["cusip"] for r in rows + exits}
        f = filings[0]
        managers.append({
            "id": mid, "person": person, "fund": fund, "sec_name": f["sec_name"], "cik": cik, "note": note, "investor": inv,
            "period": f["period"], "filed": f["filed"], "prev_period": filings[1]["period"] if len(filings) > 1 else None,
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['accession'].replace('-', '')}/",
            "total_value": sum(r["value"] for r in rows if not r["option"]), "holdings": rows, "exits": exits,
        })
        log(f"{person}：{f['sec_name']}・{f['period']}・{len(rows)} 檔")

    mapping = map_cusips(cusips)
    for m in managers:
        for r in m["holdings"] + m["exits"]:
            mp = mapping.get(r["cusip"]) or {}
            r["ticker"] = mp.get("ticker")
            r["adr"] = mp.get("type") == "Depositary Receipt"

    # 依股票彙總：幾位大佬持有、這季誰新買或加碼
    by_ticker: dict[str, dict] = {}
    for m in managers:
        for r in m["holdings"]:
            if r["option"] or not r["ticker"]:
                continue
            t = by_ticker.setdefault(r["ticker"], {"ticker": r["ticker"], "name": r["name"], "holders": [], "value": 0.0})
            t["holders"].append({"id": m["id"], "person": m["person"], "weight": round(r["weight"], 2), "change": r["change"], "chg_pct": r["chg_pct"]})
            t["value"] += r["value"]
        for r in m["exits"]:
            if r["ticker"]:
                t = by_ticker.setdefault(r["ticker"], {"ticker": r["ticker"], "name": r["name"], "holders": [], "value": 0.0})
                t.setdefault("exited_by", []).append(m["person"])
    for t in by_ticker.values():
        t["n"] = len(t["holders"])
        t["buying"] = sum(h["change"] in ("新買進", "加碼") for h in t["holders"])
        t["selling"] = sum(h["change"] == "減碼" for h in t["holders"]) + len(t.get("exited_by", []))

    OUT.write_text(json.dumps({"generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
                               "managers": managers, "by_ticker": by_ticker}, ensure_ascii=False), encoding="utf-8")
    unmapped = sum(1 for c in cusips if not (mapping.get(c) or {}).get("ticker"))
    log(f"✅ 大佬持股：{len(managers)}/{len(MANAGERS)} 位、{len(by_ticker)} 檔股票、CUSIP 對不到代號 {unmapped} 個")
    return 0 if managers else 1


if __name__ == "__main__":
    sys.exit(main())
