"""
「市場」頁：指數看板（日 K）、產業／題材熱力圖、三大法人與融資、強勢股、大戶加碼、處置／注意股、除權息行事曆。
資料來自 market.py 的 data/market/latest.json。持股提醒（holdings_alerts）只用在有密碼的 /portfolio/。
"""

import json
import re
from html import escape
from pathlib import Path

from visuals import stock_logo


def e(x) -> str:
    return escape(str(x if x is not None else ""))


def load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cls(x) -> str:
    return "pos" if (x or 0) > 0 else "neg" if (x or 0) < 0 else ""


def signed(x, d=2, unit="%") -> str:
    return "—" if x is None else f"{x:+,.{d}f}{unit}"


def roc_period(p: str | None) -> str:
    return re.sub(r"(\d{3})/(\d{2})/(\d{2})", lambda m: f"{int(m[1]) + 1911}-{m[2]}-{m[3]}", p or "")


def tabs(group: str, items: list[tuple[str, str]], active: str) -> str:
    return (f'<div class="mk-tabs" data-tabs="{group}">' + "".join(
        f'<button type="button" data-tab="{k}"{" class=\"on\"" if k == active else ""}>{e(label)}</button>' for k, label in items) + "</div>")


def panel(group: str, key: str, body: str, active: bool) -> str:
    return f'<div data-panel="{group}:{key}"{"" if active else " hidden"}>{body}</div>'


# ---------- 指數看板 ----------

def spark(values: list[float], w=120, h=32) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    pts = " ".join(f"{i / (len(values) - 1) * w:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}" for i, v in enumerate(values))
    return f'<svg class="mk-spark {cls(values[-1] - values[0])}" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polyline points="{pts}"/></svg>'


def candles(ohlc: list[list], w=1000, h=300) -> str:
    """日 K：紅漲綠跌（台灣習慣），右側價格刻度、下方月份。"""
    if len(ohlc) < 2:
        return ""
    pad_r, pad_b = 64, 22
    lo = min(r[3] for r in ohlc)
    hi = max(r[2] for r in ohlc)
    span = hi - lo or 1
    cw = (w - pad_r) / len(ohlc)
    y = lambda v: 6 + (hi - v) / span * (h - pad_b - 12)  # noqa: E731
    out = []
    for k in range(5):
        v = lo + span * k / 4
        out.append(f'<line class="grid" x1="0" x2="{w - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="ax" x="{w - pad_r + 6}" y="{y(v) + 4:.1f}">{v:,.2f}</text>')
    last_month = None
    for i, (d, o, hgh, low, c) in enumerate(ohlc):
        x = i * cw + cw / 2
        tone = "up" if c >= o else "down"
        top, bot = y(max(o, c)), y(min(o, c))
        out.append(f'<g class="{tone}"><line x1="{x:.1f}" x2="{x:.1f}" y1="{y(hgh):.1f}" y2="{y(low):.1f}"/>'
                   f'<rect x="{x - cw * 0.35:.1f}" y="{top:.1f}" width="{cw * 0.7:.1f}" height="{max(bot - top, 0.8):.1f}"/></g>')
        if d[5:7] != last_month:
            last_month = d[5:7]
            out.append(f'<text class="ax" x="{x:.1f}" y="{h - 6}">{int(d[5:7])}月</text>')
    last = ohlc[-1][4]
    out.append(f'<line class="last" x1="0" x2="{w - pad_r}" y1="{y(last):.1f}" y2="{y(last):.1f}"/>')
    return f'<svg class="mk-candles" viewBox="0 0 {w} {h}" role="img" aria-label="日 K 線">{"".join(out)}</svg>'


def index_board(indices: list[dict]) -> str:
    if not indices:
        return '<p class="empty">指數資料暫時讀不到</p>'
    cards, charts = [], []
    for i, ix in enumerate(indices):
        closes = [r[4] for r in ix["ohlc"][-40:]]
        cards.append(
            f'<button type="button" class="mk-idx{" on" if i == 0 else ""}" data-tab="{i}">'
            f'<span class="mk-idx-top"><b>{e(ix["name"])}</b><small>{e(ix["region"])}</small></span>'
            f'<span class="mk-idx-val">{ix["close"]:,.2f}</span>'
            f'<span class="mk-idx-chg {cls(ix["chg"])}">{ix["chg"]:+,.2f}（{ix["chg_pct"]:+.2f}%）</span>{spark(closes)}</button>')
        o = ix["ohlc"]
        hi, lo = max(r[2] for r in o), min(r[3] for r in o)
        charts.append(panel("idx", str(i),
            f'<div class="mk-chart-head"><b>{e(ix["name"])}</b><span class="{cls(ix["chg"])}">{ix["close"]:,.2f}　{ix["chg"]:+,.2f}（{ix["chg_pct"]:+.2f}%）</span>'
            f'<small>近半年 高 {hi:,.2f}・低 {lo:,.2f}・資料日 {e(ix["date"])}</small></div>{candles(o)}', i == 0))
    return (f'<div class="mk-idx-grid" data-tabs="idx">{"".join(cards)}</div>'
            f'<div class="mk-chart">{"".join(charts)}</div>')


# ---------- 熱力圖 ----------

def squarify(values: list[float], x=0.0, y=0.0, w=100.0, h=100.0) -> list[tuple[float, float, float, float]]:
    """Squarified treemap（Bruls 等人的演算法），回傳每塊的 (x, y, w, h)，單位是百分比。"""
    total = sum(values)
    if not values or total <= 0:
        return []
    areas = [v / total * w * h for v in values]
    rects: list = []

    def worst(row, side):
        s = sum(row)
        return max(max(side * side * r / (s * s), (s * s) / (side * side * r)) for r in row)

    def layout(row, x, y, w, h):
        s = sum(row)
        if w >= h:
            col_w = s / h
            yy = y
            for r in row:
                rects.append((x, yy, col_w, r / col_w))
                yy += r / col_w
            return x + col_w, y, w - col_w, h
        row_h = s / w
        xx = x
        for r in row:
            rects.append((xx, y, r / row_h, row_h))
            xx += r / row_h
        return x, y + row_h, w, h - row_h

    row: list = []
    i = 0
    while i < len(areas):
        side = min(w, h)
        a = areas[i]
        if not row or worst(row + [a], side) <= worst(row, side):
            row.append(a)
            i += 1
        else:
            x, y, w, h = layout(row, x, y, w, h)
            row = []
    if row:
        layout(row, x, y, w, h)
    return rects


def heat_color(pct: float) -> str:
    # 紅漲綠跌；±4% 以上顏色最深
    t = max(-1.0, min(1.0, pct / 4))
    if abs(pct) < 0.05:
        return "var(--heat-flat)"
    mix = round(25 + abs(t) * 75)
    base = "var(--pos)" if t > 0 else "var(--neg)"
    return f"color-mix(in srgb, {base} {mix}%, var(--heat-flat))"


def treemap(groups: list[dict], limit: int = 24) -> str:
    groups = groups[:limit]
    rects = squarify([g["tv"] for g in groups])
    tiles = []
    for g, (x, y, w, h) in zip(groups, rects):
        tops = "、".join(f'{t["name"]} {t["pct"]:+.1f}%' for t in g["top"])
        size = "lg" if w * h > 600 else "md" if w * h > 150 else "sm" if w * h > 45 and min(w, h) > 4 else "xs"
        tiles.append(
            f'<div class="mk-tile {size}" style="left:{x:.2f}%;top:{y:.2f}%;width:{w:.2f}%;height:{h:.2f}%;background:{heat_color(g["pct"])}" '
            f'title="{e(g["name"])} {g["pct"]:+.2f}%｜上漲 {g["up"]}/{g["n"]} 檔｜{e(tops)}">'
            f'<b>{e(g["name"])}</b><span>{g["pct"]:+.2f}%</span>'
            + (f'<small>{e(tops)}</small>' if size == "lg" else "") + "</div>")
    return f'<div class="mk-tree">{"".join(tiles)}</div>'


def breadth_bar(b: dict) -> str:
    total = b["up"] + b["down"] + b["flat"] or 1
    return (f'<div class="mk-breadth"><div class="bar"><i class="up" style="width:{b["up"] / total * 100:.1f}%"></i>'
            f'<i class="flat" style="width:{b["flat"] / total * 100:.1f}%"></i><i class="down" style="width:{b["down"] / total * 100:.1f}%"></i></div>'
            f'<div class="legend"><span class="pos">上漲 {b["up"]}（漲停 {b["limit_up"]}）</span><span>平盤 {b["flat"]}</span>'
            f'<span class="neg">下跌 {b["down"]}（跌停 {b["limit_down"]}）</span></div></div>')


# ---------- 三大法人與融資 ----------

def flow_bars(hist: list[dict], key: str, w=1000, h=160) -> str:
    vals = [x.get(key) for x in hist]
    if not any(v is not None for v in vals):
        return ""
    m = max(abs(v) for v in vals if v is not None) or 1
    bw = w / len(vals)
    mid = h / 2
    bars = []
    for i, (d, v) in enumerate(zip(hist, vals)):
        if v is None:
            continue
        bh = abs(v) / m * (mid - 6)
        y = mid - bh if v > 0 else mid
        bars.append(f'<rect class="{"up" if v > 0 else "down"}" x="{i * bw + bw * 0.15:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" height="{max(bh, 0.6):.1f}"><title>{d["date"]} {v:+,.1f} 億</title></rect>')
    return (f'<svg class="mk-bars" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><line class="grid" x1="0" x2="{w}" y1="{mid}" y2="{mid}"/>{"".join(bars)}</svg>'
            f'<div class="mk-axis"><span>{e(hist[0]["date"])}</span><span>單位：億元・最大 {m:,.0f} 億</span><span>{e(hist[-1]["date"])}</span></div>')


def margin_line(hist: list[dict], w=1000, h=160) -> str:
    pts = [(i, x["margin_yi"]) for i, x in enumerate(hist) if x.get("margin_yi")]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    span = hi - lo or 1
    n = len(hist) - 1 or 1
    line = " ".join(f"{i / n * w:.1f},{h - 8 - (v - lo) / span * (h - 16):.1f}" for i, v in pts)
    return (f'<svg class="mk-line" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polyline points="{line}"/></svg>'
            f'<div class="mk-axis"><span>{e(hist[0]["date"])}</span><span>融資餘額 {lo:,.0f}～{hi:,.0f} 億</span><span>{e(hist[-1]["date"])}</span></div>')


def institutions(hist: list[dict]) -> str:
    if not hist:
        return '<p class="empty">法人資料暫時讀不到</p>'
    t = hist[-1]
    tiles = [("外資", t.get("foreign")), ("投信", t.get("trust")), ("自營商", t.get("dealer")), ("三大法人合計", t.get("total"))]
    body = '<div class="stats">' + "".join(
        f'<div class="stat"><div class="stat-label">{k}</div><div class="stat-value {cls(v)}">{signed(v, 1, "")}<span class="unit">億</span></div>'
        f'<div class="stat-foot"><span>上市・{e(t["date"])}</span></div></div>' for k, v in tiles)
    if t.get("margin_yi") is not None:
        body += (f'<div class="stat"><div class="stat-label">融資餘額</div><div class="stat-value">{t["margin_yi"]:,.0f}<span class="unit">億</span></div>'
                 f'<div class="stat-foot"><span class="{cls(t.get("margin_chg_yi"))}">單日 {signed(t.get("margin_chg_yi"), 1, " 億")}</span></div></div>')
    body += "</div>"
    groups = [("foreign", "外資"), ("trust", "投信"), ("total", "三大法人"), ("margin", "融資餘額")]
    body += tabs("flow", groups, "foreign")
    for k, _ in groups:
        body += panel("flow", k, margin_line(hist) if k == "margin" else flow_bars(hist, k), k == "foreign")
    return body


# ---------- 強勢股、大戶 ----------

def rank_list(rows: list[dict], key: str, foot) -> str:
    if not rows:
        return '<p class="empty">暫無資料</p>'
    return '<ol class="mk-rank">' + "".join(
        f'<li><span class="n">{i}</span>{stock_logo(r["code"], r["name"], r.get("market"), "sm")}'
        f'<span class="nm"><b>{e(r["name"])}</b><small>{e(r["code"])}・{e(foot(r))}</small></span>'
        f'<b class="{cls(r[key])}">{r[key]:+.2f}{"%" if key != "big_chg" else " 個百分點"}</b></li>'
        for i, r in enumerate(rows, 1)) + "</ol>"


def strong(s: dict) -> str:
    if not s:
        return '<p class="empty">暫無資料</p>'
    items = [("d", "今日"), ("w", "近 5 日"), ("m", "近 20 日")]
    return (tabs("strong", items, "w")
            + "".join(panel("strong", k, rank_list(s.get(k, [])[:10], k, lambda r: f'{r.get("industry") or ""} {r["price"]:,.2f}'), k == "w") for k, _ in items)
            + '<p class="mk-note">範圍：成交值前 250 名、持股、供應鏈與研究名單（約 300 檔）</p>')


def big_holders(b: dict) -> str:
    if not b or not b.get("prev"):
        return (f'<p class="empty">集保戶股權分散表每週五更新；已存下 {e((b or {}).get("date") or "本週")} 的資料，'
                '下週起就能比出「400 張以上大戶持股比例」的週變化。</p>')
    return (f'<p class="mk-note">{e(b["prev"])} → {e(b["date"])}，400 張以上大戶持股比例變化（股東 1,000 人以上的公司）</p>'
            + tabs("big", [("up", "大戶加碼"), ("down", "大戶減碼")], "up")
            + panel("big", "up", rank_list(b["up"][:10], "big_chg", lambda r: f'大戶 {r["big"]:.1f}%・股東 {r["holders_chg"]:+,} 人'), True)
            + panel("big", "down", rank_list(b["down"][:10], "big_chg", lambda r: f'大戶 {r["big"]:.1f}%・股東 {r["holders_chg"]:+,} 人'), False))


# ---------- 處置／注意股、除權息 ----------

LEVEL_CLASS = {"處置中": "bad", "可能處置": "warn", "注意": "note"}


def warning_cards(ws: list[dict]) -> str:
    if not ws:
        return '<p class="empty">今天沒有處置或注意股</p>'
    counts = {k: sum(w["level"] == k for w in ws) for k in LEVEL_CLASS}
    items = [(k, f"{k} {counts[k]}") for k in LEVEL_CLASS]
    out = tabs("warn", items, "處置中")
    for k in LEVEL_CLASS:
        rows = [w for w in ws if w["level"] == k and re.fullmatch(r"\d{4}", w["code"])]
        cards = "".join(
            f'<div class="mk-warn {LEVEL_CLASS[k]}"><div class="mk-warn-head">{stock_logo(w["code"], w["name"], w["market"], "sm")}'
            f'<b>{e(w["name"])}</b><small>{e(w["code"])}・{e(w["market"])}</small><span class="lv">{e(k)}</span></div>'
            + (f'<p class="period">處置期間 {e(roc_period(w["period"]))}</p>' if w.get("period") else "")
            + f'<p>{e((w["detail"] or "")[:90])}{"…" if len(w["detail"] or "") > 90 else ""}</p></div>' for w in rows[:30])
        out += panel("warn", k, f'<div class="mk-warn-grid">{cards or "<p class=empty>無</p>"}</div>', k == "處置中")
    return out + '<p class="mk-note">處置股改為人工撮合（約每 5～20 分鐘一次），部分需預收款券；「可能處置」是注意次數已接近處置標準。</p>'


def calendar(xs: list[dict], days: int = 10) -> str:
    if not xs:
        return '<p class="empty">近期沒有除權息</p>'
    dates = sorted({x["date"] for x in xs})[:days]
    out = []
    for d in dates:
        rows = [x for x in xs if x["date"] == d]
        stocks = [x for x in rows if not x["code"].startswith("00")]
        etfs = [x for x in rows if x["code"].startswith("00")]

        def row(x):
            amt = f'現金 {x["cash"]:.4g} 元' if x.get("cash") else ""
            if x.get("stock"):
                amt += f'{"・" if amt else ""}配股 {x["stock"]:.4g}'
            return (f'<li><span class="pill">{e(x["type"])}</span><b>{e(x["name"])}</b><small>{e(x["code"])}</small>'
                    f'<span class="amt">{e(amt)}</span></li>')
        body = "".join(row(x) for x in stocks)
        if etfs:
            body += f'<li class="etf"><details><summary>ETF {len(etfs)} 檔</summary><ul>{"".join(row(x) for x in etfs)}</ul></details></li>'
        out.append(f'<div class="mk-day"><h4>{int(d[5:7])}/{int(d[8:])}<small>{len(rows)} 檔</small></h4><ul>{body}</ul></div>')
    return f'<div class="mk-cal">{"".join(out)}</div><p class="mk-note">法說會沒有公開的開放資料，暫不列入。</p>'


TAB_SCRIPT = """<script>
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-tabs] [data-tab]");
  if (!b) return;
  const group = b.closest("[data-tabs]").dataset.tabs;
  b.parentElement.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(`[data-panel^="${group}:"]`).forEach((p) => { p.hidden = p.dataset.panel !== `${group}:${b.dataset.tab}`; });
});
</script>"""


def render(m: dict | None, hero, section) -> str:
    if not m:
        return hero("市場", "市場資料準備中", "下一次網站更新後就會出現。")
    date = (m.get("history") or [{}])[-1].get("date") or m["generated_at"][:10]
    body = hero("市場", "今天市場怎麼走", f"指數、產業熱力圖、法人與融資、強勢股、處置股與除權息，一頁看完・台股資料日 {e(date)}")
    body += '<main class="wrap">'
    body += section("指數看板", index_board(m.get("indices", [])), "點卡片看近半年日 K")
    heat = (tabs("heat", [("ind", "上市櫃產業"), ("theme", "供應鏈題材")], "ind")
            + panel("heat", "ind", treemap(m.get("industries", [])), True)
            + panel("heat", "theme", treemap(m.get("themes", [])), False)
            + breadth_bar(m["breadth"]))
    body += section("市場熱力圖", heat, "面積＝成交值・顏色＝成交值加權漲跌（紅漲綠跌）")
    body += section("三大法人與融資", institutions(m.get("history", [])), "上市・近 60 個交易日")
    body += ('<div class="two-col">' + section("強勢股", strong(m.get("strong", {})))
             + section("大戶加碼", big_holders(m.get("big_holders", {})), "集保・每週") + "</div>")
    body += section("處置／注意股預警", warning_cards(m.get("warnings", [])), "證交所・櫃買中心公告")
    body += section("除權息行事曆", calendar(m.get("ex_dividends", [])), "未來 10 個除權息日")
    return body + "</main>" + TAB_SCRIPT


def holdings_alerts(holdings: list[dict], m: dict | None) -> str:
    """只放在 /portfolio/：持股是否在處置／注意名單、近期是否除權息（含預估配息金額）。"""
    if not m:
        return ""
    held = {h["code"]: h for h in holdings}
    items = []
    for w in m.get("warnings", []):
        if w["code"] in held:
            items.append(f'<li class="mk-alert {LEVEL_CLASS[w["level"]]}"><span class="lv">{e(w["level"])}</span><b>{e(held[w["code"]]["name"])}</b>'
                         f'<small>{e(roc_period(w.get("period")) or (w["detail"] or "")[:60])}</small></li>')
    for x in m.get("ex_dividends", []):
        h = held.get(x["code"])
        if h:
            est = f'・預估現金 {x["cash"] * (h.get("shares") or 0):,.0f} 元' if x.get("cash") and h.get("shares") else ""
            items.append(f'<li class="mk-alert div"><span class="lv">{e(x["type"])}</span><b>{e(h["name"])}</b>'
                         f'<small>{e(x["date"])}・每股 {x.get("cash") or 0:.4g} 元{e(est)}</small></li>')
    if not items:
        return '<p class="empty">持股目前沒有處置、注意，近期也沒有除權息。</p>'
    return f'<ul class="mk-alerts">{"".join(items)}</ul>'
