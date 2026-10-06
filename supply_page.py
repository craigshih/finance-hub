"""
/supply/ 供應鏈地圖頁面：本日最強龍頭 → 點選龍頭 → 關係圖＋台股供應鏈清單；以及台股反查。
資料：data/supply/latest.json（supply.py 產生）。切換龍頭由 static/site.js 處理，不用重新載入頁面。
"""

import json
import math
from pathlib import Path

from supply_map import LEADERS
from visuals import e, sparkline, stock_logo

REL_CLASS = {"供應商": "sup", "客戶": "cus", "同業": "peer", "合作": "part"}
REL_NOTE = {
    "供應商": "台廠賣產品或代工給它：它的需求好，台廠訂單可能跟著好",
    "客戶": "台廠向它買設備：台廠擴產時它受惠，方向相反",
    "同業": "同產業、景氣連動（例如記憶體報價）",
    "合作": "合資、代理或策略合作",
}


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pct_span(x, digits=2) -> str:
    if x is None:
        return "—"
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="{cls}">{x:+.{digits}f}%</span>'


def leader_logo(ld: dict, size: str = "sm") -> str:
    return stock_logo(LEADERS[ld["code"]][2], ld["name"], None, size)


def network(ld: dict, rows: list[dict]) -> str:
    """關係圖：龍頭在中間，台股公司圍成一圈；線的樣式代表關係，圓點顏色代表今天漲跌。"""
    w, h, cx, cy = 640, 440, 320, 220
    n = len(rows)
    r = 165 if n > 8 else 140
    edges, nodes = [], []
    for i, t in enumerate(rows):
        a = -math.pi / 2 + 2 * math.pi * i / n
        x, y = cx + r * math.cos(a) * 1.25, cy + r * math.sin(a)
        rel = t["links"][ld["code"]][0]
        chg = t.get("chg_1d") or 0
        tone = "pos" if chg > 0 else "neg" if chg < 0 else "flat"
        strength = min(abs(chg) / 4, 1)
        edges.append(f'<line class="edge {REL_CLASS.get(rel, "sup")}" x1="{cx}" y1="{cy}" x2="{x:.0f}" y2="{y:.0f}" style="--i:{i}"/>')
        nodes.append(
            f'<g class="node {tone}" style="--i:{i};--s:{strength:.2f}" transform="translate({x:.0f} {y:.0f})">'
            f'<circle r="21"/><text class="nn" y="-28">{e(t["name"].replace("*", ""))}</text>'
            f'<text class="nc" y="5">{chg:+.1f}%</text></g>')
    center = (f'<g class="center" transform="translate({cx} {cy})"><circle r="44"/>'
              f'<text y="-4">{e(ld["name"])}</text><text class="cc" y="16">{ld["chg_1d"]:+.2f}%</text></g>')
    return (f'<svg class="net" viewBox="0 0 {w} {h}" role="img" aria-label="{e(ld["name"])}的台股供應鏈關係圖">'
            f'{"".join(edges)}{"".join(nodes)}{center}</svg>')


def flow_cell(f: dict | None) -> str:
    if not f:
        return '<span class="muted">—</span>'
    net = (f.get("foreign_lots") or 0) + (f.get("trust_lots") or 0)
    cls = "pos" if net > 0 else "neg" if net < 0 else ""
    return f'<span class="{cls}">{net:+,}</span><small>張・{f.get("buy_days", 0)}/5 天買超</small>'


def leader_panel(ld: dict, rows: list[dict], selected: bool) -> str:
    if not rows:
        return ""
    ups = sum(1 for t in rows if (t.get("chg_1d") or 0) > 0)
    avg = sum(t.get("chg_1d") or 0 for t in rows) / len(rows)
    us = ld["market"] == "美股"
    timing = ("美股收盤在台股開盤之前，可以對照「龍頭上一個交易日」與「台股今天」的反應。" if us
              else "日股、韓股和台股交易時間大致重疊，漲跌通常是同一天的反應。")
    order = {"供應商": 0, "合作": 1, "客戶": 2, "同業": 3}
    rows = sorted(rows, key=lambda t: (order.get(t["links"][ld["code"]][0], 9), -(t.get("chg_1d") or 0)))
    trs = "".join(
        f'<tr><td><span class="name">{stock_logo(t["code"], t["name"], t["market"], "sm")}'
        f'<span><b>{e(t["name"])}</b><small>{e(t["code"])}・{e(t["market"])}</small></span></span></td>'
        f'<td><span class="rel {REL_CLASS.get(t["links"][ld["code"]][0], "sup")}">{e(t["links"][ld["code"]][0])}</span></td>'
        f'<td class="role">{e(t["links"][ld["code"]][1])}</td>'
        f'<td class="num">{pct_span(t.get("chg_1d"))}</td><td class="num">{pct_span(t.get("chg_5d"))}</td>'
        f'<td class="num flowc">{flow_cell(t.get("flows"))}</td>'
        f'<td class="sparkc">{sparkline(t.get("spark"), 100, 28)}</td></tr>'
        for t in rows)
    return f"""<div class="lpanel" data-leader="{e(ld['code'])}"{'' if selected else ' hidden'}>
  <div class="lhead">{leader_logo(ld, 'lg')}
    <div><h3>{e(ld['name'])}<small>{e(ld['market'])}・{e(ld['industry'])}</small></h3>
    <p class="muted">最新收盤 {ld['price']:,.2f}（{e(ld['date'])}）・單日 {pct_span(ld['chg_1d'])}・5 日 {pct_span(ld['chg_5d'])}</p></div>
    <div class="lspark">{sparkline(ld.get('spark'), 220, 56)}</div></div>
  <p class="transmit"><b>傳導觀察</b>{len(rows)} 家台股相關公司今天平均 {pct_span(avg)}，{ups} 家上漲、{len(rows) - ups} 家下跌或平盤。{timing}</p>
  <div class="netwrap">{network(ld, rows)}</div>
  <div class="legend rel-legend">{''.join(f'<span><i class="ln {c}"></i>{e(k)}：{e(REL_NOTE[k])}</span>' for k, c in REL_CLASS.items())}</div>
  <div class="table-wrap"><table class="holdings chain"><thead><tr><th>台股公司</th><th>關係</th><th>角色</th><th class="num">今日</th><th class="num">5 日</th>
  <th class="num">法人 5 日（外資＋投信）</th><th>20 日走勢</th></tr></thead><tbody>{trs}</tbody></table></div>
</div>"""


def render(data: dict | None, prefix: str = "../") -> str:
    from build import hero, section  # 避免循環匯入

    body = hero("供應鏈地圖", "海外龍頭 → 台股供應鏈",
                "看美股、日股、韓股龍頭今天怎麼走，順著供應鏈找到相關的台股公司。")
    body += '<main class="wrap" id="supply-app">'
    if not data or not data.get("leaders"):
        return body + '<p class="empty">供應鏈資料還沒產生</p></main>'
    leaders = sorted(data["leaders"], key=lambda l: -(l.get("chg_1d") or 0))
    by_leader = {l["code"]: [t for t in data["tw"] if l["code"] in t["links"]] for l in leaders}
    top = leaders[0]["code"]

    strong = "".join(
        f'<button class="lcard{" on" if l["code"] == top else ""}" data-pick="{e(l["code"])}">{leader_logo(l)}'
        f'<span class="lc-name"><b>{e(l["name"])}</b><small>{e(l["market"])}・{len(by_leader[l["code"]])} 家台股</small></span>'
        f'<span class="lc-chg">{pct_span(l["chg_1d"])}</span>{sparkline(l.get("spark"), 120, 30)}</button>'
        for l in leaders[:6])
    body += section("本日最強龍頭", f'<div class="lcards">{strong}</div>', "依最新一個交易日漲幅排序，點一下看它的台股供應鏈")

    markets = ["全部", "美股", "日股", "韓股"]
    tabs = "".join(f'<button class="{"on" if m == "全部" else ""}" data-market="{m}">{m}</button>' for m in markets)
    chips = "".join(
        f'<button class="lchip{" on" if l["code"] == top else ""}" data-pick="{e(l["code"])}" data-mk="{e(l["market"])}">'
        f'{leader_logo(l)}<span>{e(l["name"])}</span>{pct_span(l["chg_1d"], 1)}</button>'
        for l in sorted(leaders, key=lambda l: (markets.index(l["market"]), -(l.get("chg_1d") or 0))))
    panels = "".join(leader_panel(l, by_leader[l["code"]], l["code"] == top) for l in leaders)
    body += section("選一家龍頭", f'<div class="news-tabs" id="mk-tabs">{tabs}</div><div class="lchips">{chips}</div>{panels}',
                    f'法人資料 {e(data.get("flows_date") or "—")}（只涵蓋上市公司）')

    # 台股反查
    rev = sorted(data["tw"], key=lambda t: -len(t["links"]))
    names = {l["code"]: l for l in data["leaders"]}
    rows = "".join(
        f'<tr><td><span class="name">{stock_logo(t["code"], t["name"], t["market"], "sm")}'
        f'<span><b>{e(t["name"])}</b><small>{e(t["code"])}</small></span></span></td>'
        f'<td class="num">{pct_span(t.get("chg_1d"))}</td><td><div class="revlinks">'
        + "".join(f'<button class="mini" data-pick="{e(ld)}" title="{e(rel)}：{e(role)}">{leader_logo(names[ld])}'
                  f'<span class="rel {REL_CLASS.get(rel, "sup")}">{e(rel)}</span></button>'
                  for ld, (rel, role) in t["links"].items() if ld in names)
        + "</div></td></tr>" for t in rev)
    body += section("台股反查", '<div class="table-wrap"><table class="holdings"><thead><tr><th>台股公司</th><th class="num">今日</th>'
                    f'<th>連結到哪些海外龍頭（點 logo 跳過去）</th></tr></thead><tbody>{rows}</tbody></table></div>',
                    "連結越多的公司排越前面")
    body += ('<p class="obs-disclaimer">供應鏈關係依公開報導整理（美股部分與每週基本面分析同一份清單），屬背景知識，'
             '訂單與合作會變動，可能已過時；要修正或增加公司，改 supply_map.py 即可。股價來自 Yahoo Finance，法人買賣超來自證交所。'
             '這是研究素材，不是買賣建議。</p>')
    return body + "</main>"
