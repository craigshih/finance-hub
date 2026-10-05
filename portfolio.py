"""
投資總覽的資料：從 Notion 讀持股與交易，跟凱基對帳單逐筆核對。

- Notion「股票交易管理」：持股數、均價、市值、損益都已由「股票代號」主檔的公式算好，
  這裡直接讀公式結果，不重算一次（避免兩邊算法不一致）。
- 凱基對帳單：kgi-trade-report 每月輸出的 data/statements/{YYYY-MM}.json。
- 只讀不寫：NOTION_TOKEN 應該是一組只有 Read content 權限的 integration。

這些資料只在 build 時讀進記憶體、直接產生網頁，不寫進任何 repo。
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import requests

NOTION_TOKEN = (os.environ.get("NOTION_TOKEN") or "").strip()
TICKER_DB = "ebe40356-b27a-8346-ba19-816b30b76fdf"   # 股票代號
TRADE_DB = "2a840356-b27a-821f-973c-0159d331bcb3"    # 股票交易紀錄
DIVIDEND_DB = "06240356-b27a-8311-9aa9-81ceaa36f7d0"  # 配息紀錄
PRICE_DB = "6bf40356-b27a-8256-8a79-01b4dfdfd658"     # 股價紀錄

PRICE_TOLERANCE = 0.01  # 單價差在 1 分以內視為相同


class NotionUnavailable(Exception):
    pass


# ---------- Notion ----------

def _query(db_id: str, body: dict | None = None, limit: int | None = None) -> list[dict]:
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"}
    rows, payload = [], dict(body or {})
    while True:
        resp = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=headers, json=payload, timeout=30)
        if resp.status_code in (401, 403, 404):
            raise NotionUnavailable(f"Notion 回 {resp.status_code}：token 無效，或資料庫沒有分享給這個 integration")
        resp.raise_for_status()
        data = resp.json()
        rows.extend(data["results"])
        if not data.get("has_more") or (limit and len(rows) >= limit):
            return rows
        payload["start_cursor"] = data["next_cursor"]


def _value(prop: dict | None):
    """把 Notion 各種屬性型別攤平成 Python 值；公式/彙總取計算結果。"""
    if not prop:
        return None
    t = prop["type"]
    v = prop.get(t)
    if t in ("title", "rich_text"):
        return "".join(x["plain_text"] for x in v).strip()
    if t in ("select", "status"):
        return (v or {}).get("name")
    if t == "date":
        return (v or {}).get("start")
    if t == "relation":
        return [x["id"] for x in v]
    if t in ("formula", "rollup"):
        inner = v.get(v["type"])
        if v["type"] == "array":  # rollup 的「顯示原始值」：取第一個
            return _value(inner[0]) if inner else None
        return inner.get("start") if v["type"] == "date" and inner else inner
    return v


def _number(x) -> float | None:
    """公式有時回字串（例如 "12.3%"），統一轉成數字；百分比字串轉成比例。"""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").replace("NT$", "").strip()
    try:
        return float(s[:-1]) / 100 if s.endswith("%") else float(s)
    except ValueError:
        return None


def _clean_code(raw: str) -> str:
    # 主檔的代號欄寫成「0050 .TW」或「2330.TW」
    return re.sub(r"\s*\.TW[O]?$", "", (raw or "").strip(), flags=re.I).strip()


def load_notion() -> dict:
    if not NOTION_TOKEN:
        raise NotionUnavailable("沒有設定 NOTION_TOKEN")

    tickers = {}
    for row in _query(TICKER_DB):
        p = row["properties"]
        g = lambda name: _value(p.get(name))  # noqa: E731
        tickers[row["id"]] = {
            "code": _clean_code(g("代號")),
            "name": g("名稱"),
            "market": g("市場") or "其他",
            "shares": _number(g("庫存股數")) or _number(g("持股數")) or 0,
            "avg_cost": _number(g("買進均價 (含稅費)")),
            "cost": _number(g("庫存成本(含稅費)")),
            "price": _number(g("最新股價")),
            "value": _number(g("持股市值")),
            "unrealized": _number(g("未實現損益 (含稅費)")),
            "realized": _number(g("已實現損益 (含稅費)")),
            "dividends": _number(g("總實領配息")),
        }

    trades = []
    for row in _query(TRADE_DB):
        p = row["properties"]
        g = lambda name: _value(p.get(name))  # noqa: E731
        stock = (g("股票") or [None])[0]
        t = tickers.get(stock, {})
        trades.append({
            "date": (g("交易日") or "")[:10],
            "code": t.get("code"), "name": t.get("name"),
            "side": g("類型"), "quantity": _number(g("股數")), "price": _number(g("單價")),
            "status": g("交易狀態"), "note": g("備註"), "title": g("紀錄"),
        })

    dividends = []
    for row in _query(DIVIDEND_DB):
        p = row["properties"]
        stock = (_value(p.get("股票代號")) or [None])[0]
        t = tickers.get(stock, {})
        dividends.append({
            "date": (_value(p.get("發放日期")) or "")[:10], "code": t.get("code"), "name": t.get("name"),
            "per_share": _number(_value(p.get("股利"))), "amount": _number(_value(p.get("實領配息"))),
        })

    latest = _query(PRICE_DB, {"sorts": [{"property": "分析日期", "direction": "descending"}], "page_size": 1}, limit=1)
    price_date = (_value(latest[0]["properties"].get("分析日期")) or "")[:10] if latest else None

    return {"tickers": list(tickers.values()), "trades": trades, "dividends": dividends, "price_date": price_date}


# ---------- 彙總 ----------

def summarize(nd: dict) -> dict:
    holdings = [t for t in nd["tickers"] if (t["shares"] or 0) > 0]
    for h in holdings:
        if h["value"] is None and h["price"] is not None:
            h["value"] = h["price"] * h["shares"]
        if h["unrealized"] is None and h["value"] is not None and h["cost"] is not None:
            h["unrealized"] = h["value"] - h["cost"]
        h["return"] = h["unrealized"] / h["cost"] if h["unrealized"] is not None and h["cost"] else None
    total_value = sum(h["value"] or 0 for h in holdings)
    for h in holdings:
        h["weight"] = (h["value"] or 0) / total_value if total_value else 0
    holdings.sort(key=lambda h: -(h["value"] or 0))

    by_market = Counter()
    for h in holdings:
        by_market[h["market"]] += h["value"] or 0

    total_cost = sum(h["cost"] or 0 for h in holdings)
    unrealized = sum(h["unrealized"] or 0 for h in holdings)
    return {
        "holdings": holdings,
        "allocation": sorted(by_market.items(), key=lambda kv: -kv[1]),
        "total_value": total_value,
        "total_cost": total_cost,
        "unrealized": unrealized,
        "unrealized_pct": unrealized / total_cost if total_cost else None,
        # 已實現與配息要算全部標的（包含已出清的）
        "realized": sum(t["realized"] or 0 for t in nd["tickers"]),
        "dividends_total": sum(d["amount"] or 0 for d in nd["dividends"]),
        "recent_trades": sorted((t for t in nd["trades"] if t["status"] == "已成交"), key=lambda t: t["date"], reverse=True)[:8],
        "recent_dividends": sorted(nd["dividends"], key=lambda d: d["date"], reverse=True)[:6],
        "price_date": nd["price_date"],
    }


# ---------- 對帳 ----------

def load_statements(statement_dir: Path) -> list[dict]:
    if not statement_dir.is_dir():
        print(f"⚠️ 找不到 {statement_dir}，略過對帳", file=sys.stderr)
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(statement_dir.glob("*.json"))]


def reconcile(statements: list[dict], notion_trades: list[dict]) -> dict:
    """在對帳單涵蓋的月份裡，逐筆比對券商與 Notion 的成交紀錄。

    比對鍵：交易日、代號、買賣別、股數，單價差 ≤ PRICE_TOLERANCE。
    同一天同代號同方向但股數或單價不同 → 「數字不一致」；完全找不到 → 「只在一邊」。
    Notion 裡標記「分割調整」的紀錄不是實際成交，不參與比對。
    """
    months = sorted(s["month"] for s in statements)
    if not months:
        return {"months": [], "matched": 0, "mismatched": [], "broker_only": [], "notion_only": []}

    broker = [t for s in statements for t in s["trades"]]
    notion = [t for t in notion_trades
              if t["status"] == "已成交" and t["note"] != "分割調整" and t["date"][:7] in months]

    unmatched_notion = list(notion)
    matched, mismatched, broker_only = 0, [], []
    for b in broker:
        same = lambda n: n["date"] == b["date"] and n["code"] == b["code"] and n["side"] == b["side"]  # noqa: E731
        exact = next((n for n in unmatched_notion if same(n) and n["quantity"] == b["quantity"]
                      and n["price"] is not None and abs(n["price"] - b["price"]) <= PRICE_TOLERANCE), None)
        if exact:
            unmatched_notion.remove(exact)
            matched += 1
            continue
        near = next((n for n in unmatched_notion if same(n)), None)
        if near:
            unmatched_notion.remove(near)
            mismatched.append({"broker": b, "notion": near})
        else:
            broker_only.append(b)

    return {"months": months, "matched": matched, "mismatched": mismatched,
            "broker_only": broker_only, "notion_only": unmatched_notion}
