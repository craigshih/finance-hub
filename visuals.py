"""
網頁上的小圖與視覺元件：走勢迷你圖、季營收長條、篩選漏斗、今日觀察卡、新聞封面。
全部是內嵌 SVG／HTML，不依賴外部圖表套件；顏色用 CSS 變數，深淺色模式自動切換。
"""

import html
import json
import re
from pathlib import Path

from picks import METRIC_LABELS

STANCE_CLASS = {"偏多": "bull", "中性": "flat", "保留": "bear"}


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


# ---------- 小圖 ----------

def sparkline(values: list[float] | None, w: int = 240, h: int = 64, cls: str = "") -> str:
    """60 日收盤價走勢：線＋漸層面積＋最後一點；漲跌決定顏色（紅漲綠跌）。"""
    vals = [v for v in (values or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = [(i * (w - 4) / (len(vals) - 1) + 2, h - 4 - (v - lo) / span * (h - 8)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"2,{h} " + line + f" {pts[-1][0]:.1f},{h}"
    tone = "pos" if vals[-1] >= vals[0] else "neg"
    gid = f"g{abs(hash((tuple(vals), w))) % 10**8}"
    lx, ly = pts[-1]
    return (f'<svg class="spark {tone} {cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="currentColor" stop-opacity=".28"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/>'
            f'</linearGradient></defs><polygon points="{area}" fill="url(#{gid})"/>'
            f'<polyline class="draw" points="{line}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="currentColor"/></svg>')


def revenue_bars(quarters: list[dict] | None, w: int = 240, h: int = 70) -> str:
    qs = [q for q in (quarters or []) if q.get("revenue")][-6:]
    if len(qs) < 2:
        return ""
    top = max(q["revenue"] for q in qs)
    bw = (w - 8) / len(qs)
    bars = "".join(
        f'<rect class="bar" style="--i:{i}" x="{4 + i * bw + bw * .18:.1f}" y="{h - 14 - q["revenue"] / top * (h - 20):.1f}" '
        f'width="{bw * .64:.1f}" height="{q["revenue"] / top * (h - 20):.1f}" rx="2"/>'
        f'<text x="{4 + i * bw + bw / 2:.1f}" y="{h - 2}" text-anchor="middle">{e(q["end"][2:7].replace("-", "/"))}</text>'
        for i, q in enumerate(qs))
    return f'<svg class="revbars" viewBox="0 0 {w} {h}" aria-label="近 {len(qs)} 季營收">{bars}</svg>'


def monogram(text: str, seed: str) -> str:
    """沒有圖可放時的封面：取名稱第一個字，背景色由代號決定（同一家每次一樣）。"""
    hue = sum(map(ord, seed)) % 360
    return f'<div class="mono" style="--h:{hue}">{e((text or "?")[:1])}</div>'


def news_cover(a: dict, section_name: str) -> str:
    if a.get("thumb"):
        return f'<img class="cover" src="{e(a["thumb"])}" alt="" loading="lazy" referrerpolicy="no-referrer">'
    tag = next((k for k in a.get("keywords") or [] if len(k) <= 6), section_name)
    hue = sum(map(ord, a.get("title") or "x")) % 360
    return f'<div class="cover gen" style="--h:{hue}"><span>{e(tag)}</span></div>'


def funnel(steps: list[tuple[str, int]]) -> str:
    """篩選漏斗：寬度用對數比例，讓 1982 → 8 這種差距也看得到每一層。"""
    import math
    top = math.log10(max(steps[0][1], 10))
    rows = "".join(
        f'<div class="fstep" style="--w:{max(12, math.log10(max(n, 1)) / top * 100):.0f}%;--i:{i}">'
        f'<span class="fbar"></span><b data-count>{n:,}</b><small>{e(label)}</small></div>'
        for i, (label, n) in enumerate(steps))
    return f'<div class="funnel">{rows}</div>'


def score_bar(n_pass: int, n_total: int) -> str:
    pct = n_pass / n_total * 100 if n_total else 0
    return f'<span class="score"><i style="--p:{pct:.0f}%"></i><b>{n_pass}/{n_total}</b></span>'


# ---------- 今日觀察 ----------

def load_latest_picks(picks_dir: Path) -> dict | None:
    files = sorted(picks_dir.glob("*.json")) if picks_dir.is_dir() else []
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def _metric_chip(key: str, value) -> str:
    label, unit, note = METRIC_LABELS[key]
    if isinstance(value, bool):
        shown = "是" if value else "否"
    elif isinstance(value, float):
        shown = f"{value:,.2f}" if abs(value) < 10 else f"{value:,.1f}"
        shown += unit
    else:
        shown = f"{value:,}{unit}" if isinstance(value, int) else f"{value}{unit}"
    tone = ""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and key.endswith(("pct", "lots_5d", "100m")):
        tone = "pos" if value > 0 else "neg" if value < 0 else ""
    return f'<li title="{e(note)}"><small>{e(label)}</small><b class="{tone}">{e(shown)}</b></li>'


KEY_METRICS = {
    "台股": ["net_value_5d_100m", "buy_days_5d", "industry_rank", "rev_m_yoy_pct", "pe", "ret_20d_pct"],
    "美股": ["sector_rel_20d_pct", "cmf_20", "vol_ratio_5_50", "ret_20d_pct", "pe", "from_52w_high_pct"],
}


def short_name(name: str) -> str:
    """Advanced Micro Devices, Inc. → Advanced Micro Devices"""
    return re.sub(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Ltd\.?|plc|Co\.?|Company)$", "", name or "").strip()


def observation_card(p: dict) -> str:
    m = p.get("metrics", {})
    chips = "".join(_metric_chip(k, m[k]) for k in KEY_METRICS[p["market"]] if m.get(k) is not None)
    v = p.get("views") or {}
    personas = "".join(
        f'<div class="persona"><div class="ph"><span class="pi">{x["icon"]}</span><b>{e(x["name"])}</b>'
        f'<span class="stance {STANCE_CLASS.get(x["stance"], "flat")}">{e(x["stance"])}</span></div><p>{e(x["text"])}</p></div>'
        for x in v.get("views", []))
    watch = "".join(f"<li>{e(w)}</li>" for w in v.get("watch", []))
    news = "".join(f'<li><a href="{e(n["url"])}" target="_blank" rel="noopener">{e(n["title"])}</a></li>' for n in p.get("news", []))
    flows = p.get("top_industries") or p.get("top_sectors") or []
    flow_label = "產業 5 日法人淨流入（億元）" if p["market"] == "台股" else "類股近 20 日超額報酬（%）"
    fmax = max((abs(f.get("net_value_100m", f.get("rel_20d_pct", 0))) for f in flows), default=1) or 1
    flow_rows = "".join(
        f'<li class="{"hit" if i == (m.get("industry_rank") or m.get("sector_rank") or 0) - 1 else ""}">'
        f'<span>{e(f.get("industry") or f.get("label"))}</span>'
        f'<i style="--w:{abs(f.get("net_value_100m", f.get("rel_20d_pct", 0))) / fmax * 100:.0f}%"></i>'
        f'<b>{f.get("net_value_100m", f.get("rel_20d_pct"))}</b></li>' for i, f in enumerate(flows))
    return f"""<article class="obs">
  <header class="obs-head">
    <div class="obs-title"><span class="mkt {'tw' if p['market'] == '台股' else 'us'}">{e(p['market'])}</span>
      <h3>{e(short_name(p['name']))}<small>{e(p['code'])}</small></h3><div class="obs-sub">{e(p['industry'])}・資料日 {e(p['data_date'])}</div></div>
    <div class="obs-price"><b data-count>{p['price']:,.2f}</b><small>{'新台幣' if p['market'] == '台股' else '美元'}</small></div>
  </header>
  <div class="obs-chart">{sparkline(p.get('spark'), 520, 90, 'wide')}<small>近 60 個交易日收盤</small></div>
  {f'<p class="obs-summary">{e(v["summary"])}</p>' if v.get("summary") else ''}
  <ul class="chips">{chips}</ul>
  <div class="personas">{personas or '<p class="empty">今天沒有產生角色觀點</p>'}</div>
  <div class="obs-foot">
    <details class="fold"><summary>為什麼是它（選股規則與資金流）</summary>
      <p class="rule">{e(p.get('rule'))}</p><p class="flow-title">{flow_label}</p><ul class="flows">{flow_rows}</ul></details>
    {f'<details class="fold"><summary>接下來要追蹤</summary><ul class="watch">{watch}</ul></details>' if watch else ''}
    {f'<details class="fold"><summary>相關新聞（{len(p.get("news", []))}）</summary><ul class="watch">{news}</ul></details>' if news else ''}
  </div>
</article>"""


def observations(picks: dict | None) -> str:
    if not picks or not picks.get("picks"):
        return '<p class="empty">今天的觀察標的還沒產生</p>'
    cards = "".join(observation_card(p) for p in picks["picks"])
    return (f'<div class="obs-grid">{cards}</div>'
            '<p class="obs-disclaimer">依公開的資金流與產業趨勢規則每天自動篩選，四位角色是模擬的研究框架，由 AI 依上面的數字撰寫，'
            '可能有誤。這是研究素材，不是買賣建議，也不預測股價；任何投資決定請自行判斷。</p>')
