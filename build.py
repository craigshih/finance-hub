"""
把各個 repo 產出的資料整合成一個靜態網站（輸出到 site/）。

資料來源（由 workflow checkout 到 SOURCES_DIR 底下）：
  tim-lu/data/digests/{date}.json             每日總經摘要（macro_digest.py 產出）
  investment-team/data/reports/{date}.json    每週基本面報告的結構化資料（fundamentals.py 產出）
  investment-team/data/reports/{date}.md      同一份報告的完整文字版，放在「完整報告」頁

網站本身不打任何外部 API，只讀這些檔案；所以重建很便宜，壞了也不會影響原本寄信的流程。

版面原則：每頁先給數字與結論，長文字一律收進「展開」區塊。
"""

import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import markdown

ROOT = Path(__file__).parent
SOURCES_DIR = Path(os.environ.get("SOURCES_DIR", ROOT / "sources"))
OUT_DIR = Path(os.environ.get("OUT_DIR", ROOT / "site"))
TAIPEI = timezone(timedelta(hours=8))

DIGEST_DIR = SOURCES_DIR / "tim-lu" / "data" / "digests"
REPORT_DIR = SOURCES_DIR / "investment-team" / "data" / "reports"

NAV = [("index.html", "總覽"), ("daily/index.html", "每日總經"), ("weekly/index.html", "每週研究")]
WEEKDAYS = "一二三四五六日"
STYLE_LABEL = {"value": ("價值型", "持有 5–10 年"), "growth": ("成長型", "持有約 1 年")}
DISCLAIMER = "研究素材整理，不是買賣建議，也不預測股價。"


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def zh_date(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.year} 年 {d.month} 月 {d.day} 日・星期{WEEKDAYS[d.weekday()]}"


def pct(x, digits=1, ratio=True) -> str:
    """ratio=True 表示 0.123 → 12.3%；False 表示已經是百分比數字。"""
    if x is None:
        return "—"
    return f"{x * 100 if ratio else x:.{digits}f}%"


def num(x, digits=1) -> str:
    return "—" if x is None else f"{x:,.{digits}f}"


def signed_cls(x) -> str:
    # 台灣習慣：紅漲綠跌
    return "" if not x else ("pos" if x > 0 else "neg")


# ---------- 版面 ----------

def page(title: str, body: str, depth: int, active: str) -> str:
    prefix = "../" * depth
    nav = "".join(
        f'<a href="{prefix}{href}"{" class=\"on\"" if href == active else ""}>{label}</a>'
        for href, label in NAV
    )
    built = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(title)} · Craig 財經站</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="top"><div class="wrap">
  <a class="brand" href="{prefix}index.html"><span class="mark">C</span><span class="brand-text">Craig 財經站</span></a>
  <nav>{nav}</nav>
</div></header>
{body}
<footer><div class="wrap">更新於 {built}（台北時間）・{DISCLAIMER}</div></footer>
</body>
</html>
"""


def hero(kicker: str, title: str, sub: str = "", extra: str = "") -> str:
    sub_html = f'<p class="hero-sub">{sub}</p>' if sub else ""
    return (f'<section class="hero"><div class="wrap"><div class="kicker">{kicker}</div>'
            f'<h1>{title}</h1>{sub_html}{extra}</div></section>')


def section(title: str, body: str, note: str = "", link: str = "") -> str:
    note_html = f'<span class="sec-note">{note}</span>' if note else ""
    link_html = f'<a class="sec-link" href="{link[0]}">{link[1]} →</a>' if link else ""
    return (f'<section class="sec"><div class="sec-head"><h2>{title}</h2>{note_html}{link_html}</div>{body}</section>')


def pager(prev_href, prev_label, next_href, next_label, index_href) -> str:
    left = f'<a href="{prev_href}">← {e(prev_label)}</a>' if prev_href else "<span></span>"
    right = f'<a href="{next_href}">{e(next_label)} →</a>' if next_href else "<span></span>"
    return f'<nav class="pager">{left}<a href="{index_href}">全部日期</a>{right}</nav>'


# ---------- 每日總經 ----------

def load_digests() -> list[dict]:
    if not DIGEST_DIR.is_dir():
        print(f"⚠️ 找不到 {DIGEST_DIR}，每日總經區塊會是空的", file=sys.stderr)
        return []
    digests = []
    for f in sorted(DIGEST_DIR.glob("*.json"), reverse=True):
        try:
            digests.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️ 略過無法解析的 {f.name}：{exc}", file=sys.stderr)
    return digests


def parse_structured_summary(text: str) -> list[dict]:
    """同 macro_digest.parse_structured_summary：把『【標題】\\n- 條列』切成區塊。"""
    sections: list[dict] = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if m := re.match(r"^【(.+?)】$", line):
            current = {"header": m.group(1), "items": []}
            sections.append(current)
            continue
        item = line[2:].strip() if line.startswith(("- ", "・")) else line
        if current is None:
            current = {"header": "", "items": []}
            sections.append(current)
        current["items"].append(item)
    return sections


CITE_WORDS = ("段永平", "巴菲特", "芒格", "李錄", "FinMind", "SEC", "背景知識")


def strip_cites(text: str) -> str:
    """拿掉「【段永平】」「（段永平、李錄）」「【FinMind FY2025】」這類出處標記，用在摘要預覽。"""
    text = re.sub(r"【[^】]*】", "", text)
    text = re.sub(r"[（(]([^（）()]*)[）)]", lambda m: "" if any(w in m.group(1) for w in CITE_WORDS) else m.group(0), text)
    text = re.sub(r"[、，；\s]+([。；，]|$)", r"\1", text.replace("**", ""))
    return text.strip()


def clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n].rstrip("，、；。 ") + "…"


def fred_tiles(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">尚無總經數據</p>'
    tiles = []
    for r in rows:
        m = re.match(r"^(.*?)\s*\((.+)\)$", r.get("label", ""))
        label, unit = (m.group(1), m.group(2)) if m else (r.get("label", ""), "")
        try:
            latest = float(r["latest_value"])
            value = f"{latest:,.2f}" if latest < 1000 else f"{latest:,.0f}"
        except (TypeError, ValueError, KeyError):
            latest, value = None, e(r.get("latest_value") or "—")
        try:
            diff = latest - float(r["previous_value"])
            arrow = "▲" if diff > 0 else "▼" if diff < 0 else "–"
            change = f'<span class="chg {signed_cls(diff)}">{arrow} {abs(diff):,.2f}</span>'
        except (TypeError, ValueError, KeyError):
            change = ""
        # 「%」放在數字旁邊；較長的單位（十億美元）放在標題，避免擠到換行
        label_html = e(label) + (f"<small>・{e(unit)}</small>" if unit and unit != "%" else "")
        unit_html = '<span class="unit">%</span>' if unit == "%" else ""
        tiles.append(
            f'<div class="stat"><div class="stat-label">{label_html}</div>'
            f'<div class="stat-value">{value}{unit_html}</div>'
            f'<div class="stat-foot">{change}<span>{e(r.get("latest_date") or "")}</span></div></div>'
        )
    return '<div class="stats">' + "".join(tiles) + "</div>"


def article_lede(a: dict) -> str:
    if not a.get("structured_summary"):
        return ""
    for sec in parse_structured_summary(a["structured_summary"]):
        if sec["items"]:
            return sec["items"][0]
    return ""


def article_time(a: dict) -> str:
    return datetime.fromtimestamp(a["publishAt"], tz=TAIPEI).strftime("%m/%d %H:%M") if a.get("publishAt") else ""


def render_article(a: dict) -> str:
    meta = " ・ ".join(x for x in [e(a.get("author")), article_time(a)] if x)
    lede = article_lede(a)
    full = ""
    if a.get("structured_summary"):
        parts = ""
        for sec in parse_structured_summary(a["structured_summary"]):
            head = f"<h4>{e(sec['header'])}</h4>" if sec["header"] else ""
            parts += head + "<ul>" + "".join(f"<li>{e(it)}</li>" for it in sec["items"]) + "</ul>"
        full = f'<details class="more"><summary>完整摘要</summary><div class="more-body">{parts}</div></details>'
    link = f'<a class="ext" href="{e(a["url"])}" target="_blank" rel="noopener">原文</a>' if a.get("url") else ""
    return (f'<article class="news"><div class="news-meta">{meta}{link}</div>'
            f'<h3>{e(a.get("title"))}</h3>'
            + (f'<p class="lede">{e(lede)}</p>' if lede else "")
            + full + "</article>")


def render_digest_page(d: dict, prev_d, next_d) -> str:
    total = sum(len(s.get("articles", [])) for s in d.get("news_sections", []))
    body = hero("每日總經", zh_date(d["date"]), f"{total} 則新聞・{len(d.get('fred', []))} 項美國總經數據")
    body += '<main class="wrap">'
    body += section("美國總經數據", fred_tiles(d.get("fred", [])), "FRED")
    for sec in d.get("news_sections", []):
        arts = sec.get("articles", [])
        if arts:
            body += section(e(sec.get("name")), '<div class="news-list">' + "".join(render_article(a) for a in arts) + "</div>",
                            f"{e(sec.get('source'))}・{len(arts)} 則")
    body += pager(prev_d and f"{prev_d['date']}.html", prev_d and prev_d["date"],
                  next_d and f"{next_d['date']}.html", next_d and next_d["date"], "index.html")
    return body + "</main>"


def headline_list(d: dict, limit: int, depth_prefix: str) -> str:
    items = []
    for sec in d.get("news_sections", []):
        for a in sec.get("articles", []):
            items.append((sec.get("name"), a))
    if not items:
        return '<p class="empty">今日沒有新聞</p>'
    lis = "".join(
        f'<li><span class="pill">{e(name)}</span><a href="{depth_prefix}daily/{d["date"]}.html">{e(a.get("title"))}</a>'
        f'<span class="time">{article_time(a)}</span></li>'
        for name, a in items[:limit]
    )
    return f'<ol class="headlines">{lis}</ol>'


# ---------- 每週研究 ----------

def load_reports() -> list[dict]:
    if not REPORT_DIR.is_dir():
        print(f"⚠️ 找不到 {REPORT_DIR}，每週研究區塊會是空的", file=sys.stderr)
        return []
    reports = []
    for f in sorted(REPORT_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️ 略過無法解析的 {f.name}：{exc}", file=sys.stderr)
            continue
        # 早期版本的 JSON 只是公司清單，沒有台股篩選
        screen, companies = (data.get("screen"), data.get("companies", [])) if isinstance(data, dict) else (None, data)
        md = f.with_suffix(".md")
        reports.append({"date": f.stem, "screen": screen, "companies": companies,
                        "md": md.read_text(encoding="utf-8") if md.exists() else None})
    return reports


def bucket(cands: list[dict]) -> dict:
    return {
        "full": [c for c in cands if c["n_fail"] == 0 and not c["flags"]],
        "near": [c for c in cands if c["n_fail"] == 1 and not c["flags"]],
        "flagged": [c for c in cands if c["flags"]],
    }


def rev_dots(c: dict) -> str:
    """近 5 期月營收年增：紅點正成長、綠點負成長。"""
    series = (c.get("detail") or {}).get("rev_yoy") or []
    dots = "".join(
        f'<i class="dot {signed_cls(v)}" title="{e(m)} {pct(v, 0)}"></i>' if v is not None else '<i class="dot"></i>'
        for m, v in series
    )
    return f'<span class="dots">{dots}</span>' if dots else "—"


def metric_cells(c: dict, style: str) -> list[str]:
    co = c.get("company") or {}
    if style == "value":
        return [pct(co.get("dividend_yield"), ratio=False), pct(co.get("roe")), num(co.get("pe"))]
    return [num(co.get("pe")), pct(co.get("gross_margin")), pct(co.get("roe"))]


METRIC_HEAD = {"value": ["殖利率", "ROE", "本益比"], "growth": ["本益比", "毛利率", "ROE"]}


def candidate_detail(c: dict) -> str:
    checks = "".join(
        f'<li class="{"ok" if ch["passed"] else "ng"}"><b>{e(ch["label"])}</b>{e(ch.get("detail"))}</li>'
        for ch in c.get("checks", [])
    )
    flags = "".join(f'<li class="flag"><b>紅旗</b>{e(f)}</li>' for f in c.get("flags", []))
    ld = c.get("leader") or {}
    leader = ""
    if ld and not ld.get("self"):
        leader = (f'<p class="leader">產業龍頭對照：<b>{e(ld.get("code"))} {e(ld.get("name"))}</b>'
                  f'　本益比 {num(ld.get("pe"))}・殖利率 {pct(ld.get("dividend_yield"), ratio=False)}'
                  f'・ROE {pct(ld.get("roe"))}・毛利率 {pct(ld.get("gross_margin"))}</p>')
    return f'<ul class="checks">{flags}{checks}</ul>{leader}'


def candidate_table(cands: list[dict], style: str, show_reason: bool = False) -> str:
    if not cands:
        return '<p class="empty">本週沒有</p>'
    heads = "".join(f'<span class="num">{h}</span>' for h in METRIC_HEAD[style])
    rows = []
    for c in cands:
        cells = "".join(f'<span class="num">{v}</span>' for v in metric_cells(c, style))
        reason = ""
        if show_reason:
            missed = [ch["label"] for ch in c.get("checks", []) if not ch["passed"]]
            reason = f'<span class="why">{e("、".join(c.get("flags") or []) or "未通過：" + "、".join(missed))}</span>'
        rows.append(
            f'<details class="row"><summary>'
            f'<span class="name"><b>{e(c.get("name"))}</b><small>{e(c.get("code"))}・{e(c.get("industry"))}</small>{reason}</span>'
            f'{cells}<span class="num">{rev_dots(c)}</span>'
            f'<span class="score">{c.get("n_pass")}/{c.get("n_total")}</span></summary>'
            f'<div class="row-body">{candidate_detail(c)}</div></details>'
        )
    head = (f'<div class="thead"><span class="name">公司</span>{heads}'
            f'<span class="num">月營收年增</span><span class="score">符合</span></div>')
    return f'<div class="ctable">{head}{"".join(rows)}</div>'


def etf_table(etfs: list[dict]) -> str:
    if not etfs:
        return ""
    rows = "".join(
        f'<tr><td><b>{e(x["id"])}</b> {e(x["name"])}</td><td class="muted">{e(x.get("theme"))}</td>'
        f'<td class="num {signed_cls(x.get("ret_1y"))}">{pct(x.get("ret_1y"))}</td>'
        f'<td class="num">{pct(x.get("yield_ttm"))}</td>'
        f'<td class="num">{"✓" if x.get("above200") else "—"}</td></tr>'
        for x in etfs
    )
    return ('<div class="table-wrap"><table><thead><tr><th>ETF</th><th>主題</th><th class="num">近一年</th>'
            f'<th class="num">殖利率</th><th class="num">200 日線上</th></tr></thead><tbody>{rows}</tbody></table></div>')


def company_card(c: dict) -> str:
    price = c.get("price") or {}
    val = c.get("valuation") or {}
    cur = "新台幣" if c.get("currency") == "TWD" else "美元"
    sections = parse_structured_summary((c.get("analysis") or {}).get("lead") or "")
    consensus = next((s for s in sections if s["header"] == "共識"), sections[0] if sections else None)
    takeaway = clip(strip_cites(consensus["items"][0]), 70) if consensus and consensus["items"] else ""
    body = "".join(
        f'<h4>{e(s["header"])}</h4><ul>' + "".join(f"<li>{e(strip_cites(it))}</li>" for it in s["items"]) + "</ul>"
        for s in sections
    )
    tag = '<span class="pill">篩選候選</span>' if c.get("from_screen") else ""
    return (
        f'<article class="co"><div class="co-head"><div><b>{e(c.get("name"))}</b><small>{e(c.get("ticker"))}</small></div>{tag}</div>'
        f'<div class="co-stats"><div><small>股價（{cur}）</small>{num(price.get("price"), 2 if (price.get("price") or 0) < 1000 else 0)}</div>'
        f'<div><small>本益比</small>{num(val.get("pe_ttm"))}</div>'
        f'<div><small>FCF 殖利率</small>{pct(val.get("fcf_yield"))}</div></div>'
        + (f'<p class="lede">{e(takeaway)}</p>' if takeaway else "")
        + (f'<details class="more"><summary>綜合分析</summary><div class="more-body">{body}</div></details>' if body else "")
        + "</article>"
    )


def render_report_page(r: dict, prev_r, next_r) -> str:
    s = r["screen"]
    extra = f'<p class="hero-note">{DISCLAIMER}四位投資人角色為模擬框架。</p>'
    if s:
        counts = {st: bucket(s.get(st, [])) for st in STYLE_LABEL}
        n_full = sum(len(b["full"]) for b in counts.values())
        sub = f'全市場 {s.get("n_market", "—")} 家 → 初篩 {sum((s.get("prefilter") or {}).values())} 家 → 完全符合 {n_full} 家'
    else:
        sub = f"{len(r['companies'])} 家公司基本面分析"
    body = hero("每週研究", zh_date(r["date"]), sub, extra)
    body += '<main class="wrap">'

    if s:
        for st, (label, horizon) in STYLE_LABEL.items():
            b = counts[st]
            inner = candidate_table(b["full"], st)
            if b["near"]:
                inner += (f'<details class="fold"><summary>差一項（{len(b["near"])}）</summary>'
                          f'{candidate_table(b["near"], st, show_reason=True)}</details>')
            if b["flagged"]:
                inner += (f'<details class="fold"><summary>紅旗排除（{len(b["flagged"])}）</summary>'
                          f'{candidate_table(b["flagged"], st, show_reason=True)}</details>')
            body += section(f"{label}候選", inner, f"{horizon}・點列展開檢查細節")
        if s.get("etfs"):
            body += section("主題 ETF", etf_table(s["etfs"]))

    if r["companies"]:
        cards = "".join(company_card(c) for c in r["companies"])
        body += section("個股分析", f'<div class="co-grid">{cards}</div>')

    if r["md"]:
        body += f'<p class="full-link"><a href="{r["date"]}-full.html">看完整文字報告 →</a></p>'
    body += pager(prev_r and f"{prev_r['date']}.html", prev_r and prev_r["date"],
                  next_r and f"{next_r['date']}.html", next_r and next_r["date"], "index.html")
    return body + "</main>"


def render_full_report(r: dict) -> str:
    md = markdown.Markdown(extensions=["tables", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2-3"}})
    html_body = re.sub(r"^<h1[^>]*>.*?</h1>", "", md.convert(r["md"]), count=1, flags=re.S)
    toc = f'<details class="fold toc"><summary>目錄</summary>{md.toc}</details>' if md.toc_tokens else ""
    return (hero("每週研究・完整報告", zh_date(r["date"]), f'<a href="{r["date"]}.html">← 回到精簡版</a>')
            + f'<main class="wrap">{toc}<div class="prose">{html_body}</div></main>')


def home_candidates(r: dict) -> str:
    s = r["screen"]
    if not s:
        return '<p class="empty">本週報告沒有台股篩選</p>'
    cols = []
    for st, (label, horizon) in STYLE_LABEL.items():
        full = bucket(s.get(st, []))["full"]
        items = "".join(
            f'<li><b>{e(c["name"])}</b><small>{e(c["code"])}・{e(c.get("industry"))}</small>'
            f'<span class="num">{metric_cells(c, st)[0]}</span></li>'
            for c in full
        ) or '<li class="empty">本週沒有</li>'
        cols.append(f'<div class="pick"><div class="pick-head">{label}<small>{horizon}・{METRIC_HEAD[st][0]}</small></div><ul>{items}</ul></div>')
    return f'<div class="picks">{"".join(cols)}</div>'


# ---------- 組裝 ----------

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def date_index(kicker: str, title: str, items: list[tuple[str, str, str]]) -> str:
    body = hero(kicker, title)
    if not items:
        return body + '<main class="wrap"><p class="empty">尚無資料</p></main>'
    cards = "".join(f'<a class="date-card" href="{href}"><b>{e(label)}</b><small>{e(sub)}</small></a>' for href, label, sub in items)
    return body + f'<main class="wrap"><div class="date-grid">{cards}</div></main>'


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    shutil.copy(ROOT / "static" / "style.css", OUT_DIR / "style.css")
    shutil.copy(ROOT / "static" / "_headers", OUT_DIR / "_headers")

    digests = load_digests()  # 新 → 舊
    for i, d in enumerate(digests):
        older = digests[i + 1] if i + 1 < len(digests) else None
        newer = digests[i - 1] if i > 0 else None
        write(OUT_DIR / "daily" / f"{d['date']}.html", page(f"每日總經 {d['date']}", render_digest_page(d, older, newer), 1, "daily/index.html"))
    write(OUT_DIR / "daily" / "index.html", page("每日總經", date_index("每日總經", "歷史摘要", [
        (f"{d['date']}.html", d["date"], f"{sum(len(s.get('articles', [])) for s in d.get('news_sections', []))} 則新聞")
        for d in digests]), 1, "daily/index.html"))

    reports = load_reports()
    for i, r in enumerate(reports):
        older = reports[i + 1] if i + 1 < len(reports) else None
        newer = reports[i - 1] if i > 0 else None
        write(OUT_DIR / "weekly" / f"{r['date']}.html", page(f"每週研究 {r['date']}", render_report_page(r, older, newer), 1, "weekly/index.html"))
        if r["md"]:
            write(OUT_DIR / "weekly" / f"{r['date']}-full.html", page(f"完整報告 {r['date']}", render_full_report(r), 1, "weekly/index.html"))
    write(OUT_DIR / "weekly" / "index.html", page("每週研究", date_index("每週研究", "歷史報告", [
        (f"{r['date']}.html", r["date"], f"{len(r['companies'])} 家個股分析" + ("・含台股篩選" if r["screen"] else ""))
        for r in reports]), 1, "weekly/index.html"))

    # 總覽
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    body = hero("總覽", zh_date(today), "今天的總經數據、頭條新聞與本週研究候選，一頁看完。")
    body += '<main class="wrap">'
    if digests:
        d = digests[0]
        body += section("美國總經數據", fred_tiles(d.get("fred", [])), f"FRED・{d['date']}")
        body += section("今日頭條", headline_list(d, 6, ""), "", (f"daily/{d['date']}.html", "看全部摘要"))
    else:
        body += section("每日總經", '<p class="empty">第一份每日摘要產生後會出現在這裡</p>')
    if reports:
        r = reports[0]
        body += section("本週研究候選", home_candidates(r), f"{r['date']}・完全符合條件", (f"weekly/{r['date']}.html", "看完整研究"))
    body += section("投資總覽", '<div class="soon">Notion 交易紀錄 × 凱基對帳單　建置中</div>')
    body += "</main>"
    write(OUT_DIR / "index.html", page("總覽", body, 0, "index.html"))

    print(f"✅ 產生 {len(digests)} 份每日總經、{len(reports)} 份每週研究 → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
