"""
「大佬持股」頁（/whales/）：十位知名投資人最新 13F 持股、這季的買賣、以及大佬持有的美股連到哪些台股供應鏈。
資料來自 whales.py 的 data/whales/latest.json；供應鏈關係來自 supply_map.py（每條都有新聞出處）。
"""

import json
from html import escape
from pathlib import Path

from market_page import TAB_SCRIPT, panel, tabs
from visuals import stock_logo

CHANGE_CLASS = {"新買進": "new", "加碼": "add", "減碼": "cut", "出清": "exit", "持平": "flat"}


def e(x) -> str:
    return escape(str(x if x is not None else ""))


def load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def usd(v: float) -> str:
    return f"{v / 1e8:,.1f} 億美元" if v >= 1e8 else f"{v / 1e6:,.0f} 百萬美元"


def badge(change: str | None, pct: float | None = None) -> str:
    if not change:
        return ""
    extra = f" {pct:+.0f}%" if pct is not None and change in ("加碼", "減碼") else ""
    return f'<span class="wb {CHANGE_CLASS.get(change, "flat")}">{e(change)}{e(extra)}</span>'


def leader_suppliers() -> dict[str, list[dict]]:
    """美股龍頭 → 台股（只有新聞出處核對過的關係）。台積電 ADR 直接對到台積電。"""
    from supply_map import SOURCES, TW_MAP

    out: dict[str, list[dict]] = {"TSM": [{"code": "2330", "name": "台積電", "relation": "本尊", "note": "台積電在美國掛牌的 ADR", "source": None}]}
    for code, t in TW_MAP.items():
        for leader, (rel, note, src) in t["links"].items():
            if rel == "同業" or src not in SOURCES:
                continue
            s = SOURCES[src]
            out.setdefault(leader, []).append({"code": code, "name": t["name"], "relation": rel, "note": note,
                                               "source": {"publisher": s[0], "date": s[1], "title": s[2], "url": s[3]}})
    return out


def tw_moves(supply: dict | None) -> dict[str, dict]:
    return {t["code"]: t for t in (supply or {}).get("tw", [])}


def holder_chips(holders: list[dict]) -> str:
    return "".join(f'<span class="wh {CHANGE_CLASS.get(h["change"] or "", "flat")}" title="{e(h["person"])}：占其組合 {h["weight"]:.1f}%">'
                   f'{e(h["person"])}{badge(h["change"], h.get("chg_pct"))}</span>' for h in sorted(holders, key=lambda h: -h["weight"]))


def consensus(w: dict) -> str:
    rows = sorted(w["by_ticker"].values(), key=lambda t: (-t["n"], -t["buying"], -t["value"]))[:12]
    cards = "".join(
        f'<article class="wcard"><header>{stock_logo(t["ticker"], t["name"], "美股", "")}<div><b>{e(t["ticker"])}</b><small>{e(t["name"].title())}</small></div>'
        f'<span class="wn"><b>{t["n"]}</b> 位</span></header><div class="whs">{holder_chips(t["holders"])}</div>'
        f'<p class="wfoot">合計 {usd(t["value"])}・本季買進 {t["buying"]} 位／賣出 {t["selling"]} 位</p></article>' for t in rows)
    return f'<div class="wgrid">{cards}</div>'


def to_taiwan(w: dict, supply: dict | None) -> str:
    sup = leader_suppliers()
    moves = tw_moves(supply)
    rows = sorted((t for t in w["by_ticker"].values() if t["ticker"] in sup), key=lambda t: (-t["n"], -t["buying"]))
    if not rows:
        return '<p class="empty">這一季大佬持有的美股裡，還沒有供應鏈地圖已查證的龍頭。</p>'
    out = []
    for t in rows:
        tws = []
        for s in sup[t["ticker"]]:
            mv = moves.get(s["code"]) or {}
            chg = mv.get("chg_1d")
            src = s["source"]
            link = (f'<a href="{e(src["url"])}" target="_blank" rel="noopener" title="{e(src["title"] or src["publisher"])}">📰 {e(src["publisher"])}</a>'
                    if src and src.get("url") else "")
            tws.append(f'<li>{stock_logo(s["code"], s["name"], None, "sm")}<span><b>{e(s["name"])}</b><small>{e(s["code"])}・{e(s["relation"])}・{e(s["note"])}</small></span>'
                       + (f'<i class="{"pos" if chg > 0 else "neg" if chg < 0 else ""}">{chg:+.2f}%</i>' if chg is not None else "")
                       + f'{link}</li>')
        out.append(f'<article class="wchain"><div class="wus">{stock_logo(t["ticker"], t["name"], "美股", "lg")}'
                   f'<div><b>{e(t["ticker"])}</b><small>{t["n"]} 位大佬持有・本季買進 {t["buying"]} 位</small><div class="whs">{holder_chips(t["holders"])}</div></div></div>'
                   f'<div class="warrow" aria-hidden="true"></div><ul class="wtw">{"".join(tws)}</ul></article>')
    return ('<div class="wchains">' + "".join(out) + '</div><p class="mk-note">台股端只列供應鏈地圖裡有新聞或公司資料出處的關係（點 📰 看原文）；漲跌為最近交易日。</p>')


def quarter_moves(w: dict) -> str:
    buys, sells = [], []
    for m in w["managers"]:
        for r in m["holdings"]:
            if r["change"] in ("新買進", "加碼") and not r["option"]:
                buys.append((m, r))
        for r in m["exits"]:
            sells.append((m, r))
        for r in m["holdings"]:
            if r["change"] == "減碼" and not r["option"]:
                sells.append((m, r))

    def li(m, r):
        return (f'<li>{stock_logo(r.get("ticker") or r["cusip"], r["name"], "美股", "sm")}<span><b>{e(r.get("ticker") or r["name"])}</b>'
                f'<small>{e(m["person"])}・{usd(r["value"])}</small></span>{badge(r["change"], r.get("chg_pct"))}</li>')
    buys.sort(key=lambda x: -x[1]["value"])
    sells.sort(key=lambda x: -x[1]["value"])
    return ('<div class="two-col">'
            f'<div><h3 class="wh3">買進與加碼（依金額）</h3><ul class="wlist">{"".join(li(*x) for x in buys[:12]) or "<li class=empty>本季沒有</li>"}</ul></div>'
            f'<div><h3 class="wh3">減碼與出清（依金額）</h3><ul class="wlist">{"".join(li(*x) for x in sells[:12]) or "<li class=empty>本季沒有</li>"}</ul></div>'
            '</div>')


def manager_block(m: dict, top: int = 10) -> str:
    rows = [r for r in m["holdings"] if not r["option"]][:top]
    mx = max((r["weight"] for r in rows), default=1) or 1
    bars = "".join(
        f'<li>{stock_logo(r.get("ticker") or r["cusip"], r["name"], "美股", "sm")}<span class="wnm"><b>{e(r.get("ticker") or "—")}</b><small>{e(r["name"].title())}</small></span>'
        f'<span class="wbar"><i style="width:{r["weight"] / mx * 100:.1f}%"></i></span><span class="wpct">{r["weight"]:.1f}%</span>{badge(r["change"], r.get("chg_pct"))}</li>'
        for r in rows)
    exits = "、".join(e(r.get("ticker") or r["name"]) for r in m["exits"][:8])
    opts = [r for r in m["holdings"] if r["option"]]
    notes = ""
    if not rows and opts:
        notes += (f'<p class="wexit">這份申報只有選擇權部位：'
                  + "、".join(f'{e(r.get("ticker") or r["name"])} {"看跌" if r["option"] == "PUT" else "看漲"}' for r in opts[:8]) + "</p>")
    from datetime import date
    if (date.today() - date.fromisoformat(m["period"])).days > 200:
        notes += f'<p class="wexit">⚠︎ 最新申報停在 {e(m["period"])}，之後沒有新的 13F（可能已不需申報或停止申報），資料偏舊。</p>'
    return (f'<div class="wmgr"><div class="wmgr-head"><div><b>{e(m["person"])}</b><small>{e(m["fund"])}・{e(m["note"])}</small></div>'
            f'<div class="wmeta">持股期間 {e(m["period"])}・申報 {e(m["filed"])}・{len(m["holdings"])} 檔・{usd(m["total_value"])}'
            f'・<a href="{e(m["url"])}" target="_blank" rel="noopener">SEC 原始申報 ↗</a></div></div>'
            f'<ol class="wbars">{bars}</ol>' + notes
            + (f'<p class="wexit">本季出清：{exits}</p>' if exits else "")
            + (f'<p class="mk-note">比較基準：上一份申報（{e(m["prev_period"])}）</p>' if m.get("prev_period") else '<p class="mk-note">只有一份申報，無法比較增減</p>')
            + "</div>")


def managers(w: dict) -> str:
    ms = w["managers"]
    return (tabs("wm", [(m["id"], m["person"]) for m in ms], ms[0]["id"])
            + "".join(panel("wm", m["id"], manager_block(m), i == 0) for i, m in enumerate(ms)))


def render(w: dict | None, supply: dict | None, hero, section) -> str:
    if not w or not w.get("managers"):
        return hero("大佬持股", "資料準備中", "SEC 13F 資料下一次更新後就會出現。")
    latest = max(m["filed"] for m in w["managers"])
    body = hero("大佬持股", "大佬在買什麼？台股誰受惠？",
                f'{len(w["managers"])} 位知名投資人的 SEC 13F 官方申報・最新申報 {e(latest)}',
                '<p class="hero-note">13F 是美國機構每季申報的美股多方持股，最晚在季末後 45 天公布，所以看到的是「上一季做了什麼」，不是即時動向；'
                '也不包含放空與非美股部位。每一筆都能點回 SEC 原始文件。</p>')
    body += '<main class="wrap">'
    body += section("大佬共同持有", consensus(w), "依持有人數排序")
    body += section("大佬持股 → 台股供應鏈", to_taiwan(w, supply), "大佬持有的美股龍頭，連到已查證的台廠", ("../supply/index.html", "看完整供應鏈地圖"))
    body += section("這一季的動作", quarter_moves(w), "跟上一份 13F 比較")
    body += section("各別大佬的最新持股", managers(w), "前十大持股與占比")
    return body + "</main>" + TAB_SCRIPT


def holdings_whales(holdings: list[dict], w: dict | None) -> str:
    """只放在 /portfolio/：我的台股持股，是哪些大佬持有之美股龍頭的供應商。"""
    if not w:
        return ""
    sup = leader_suppliers()
    held = {h["code"]: h for h in holdings}
    rows = []
    for t in sorted(w["by_ticker"].values(), key=lambda t: -t["n"]):
        mine = [s for s in sup.get(t["ticker"], []) if s["code"] in held]
        for s in mine:
            rows.append(f'<li>{stock_logo(s["code"], held[s["code"]]["name"], None, "sm")}<span><b>{e(held[s["code"]]["name"])}</b>'
                        f'<small>{e(s["relation"])} {e(t["ticker"])}・{e(s["note"])}</small></span>'
                        f'<span class="whs">{holder_chips(t["holders"])}</span></li>')
    if not rows:
        return '<p class="empty">這一季大佬持有的美股龍頭裡，沒有你持股的已查證供應鏈關係。</p>'
    return f'<ul class="wlist mine">{"".join(rows)}</ul>'
