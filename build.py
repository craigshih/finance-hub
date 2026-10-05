"""
把各個 repo 產出的資料整合成一個靜態網站（輸出到 site/）。

資料來源（由 workflow checkout 到 SOURCES_DIR 底下）：
  tim-lu/data/digests/{date}.json           每日總經摘要（macro_digest.py 產出）
  investment-team/data/reports/{date}.md    每週基本面報告（fundamentals.py 產出）

網站本身不打任何外部 API，只讀這些檔案；所以重建很便宜，壞了也不會影響原本寄信的流程。
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

SECTION_ACCENT = {"新聞重點": "accent-blue", "重要數據／人物／公司": "accent-green", "市場／產業影響": "accent-amber"}


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


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
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="top"><div class="wrap">
  <a class="brand" href="{prefix}index.html">Craig 財經站</a>
  <nav>{nav}</nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer class="wrap">資料更新：{built}（台北時間）。本站內容為個人研究整理，非投資建議。</footer>
</body>
</html>
"""


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
        if m := re.match(r"^【(.+)】$", line):
            current = {"header": m.group(1), "items": []}
            sections.append(current)
            continue
        item = line[2:].strip() if line.startswith(("- ", "・")) else line
        if current is None:
            current = {"header": "", "items": []}
            sections.append(current)
        current["items"].append(item)
    return sections


def fred_change(row: dict) -> str:
    try:
        diff = float(row["latest_value"]) - float(row["previous_value"])
    except (TypeError, ValueError, KeyError):
        return ""
    cls = "up" if diff > 0 else "down" if diff < 0 else ""
    return f'<span class="{cls}">{diff:+.2f}</span>'


def render_fred(rows: list[dict]) -> str:
    if not rows:
        return ""
    trs = "".join(
        f"<tr><td>{e(r['label'])}</td><td class=\"num\">{e(r['latest_value'])}</td>"
        f"<td class=\"num\">{fred_change(r)}</td><td class=\"muted\">{e(r['latest_date'])}</td></tr>"
        for r in rows
    )
    return (
        '<section class="card"><h2>美國總經數據（FRED）</h2><div class="scroll"><table>'
        "<thead><tr><th>指標</th><th class=\"num\">最新</th><th class=\"num\">變動</th><th>日期</th></tr></thead>"
        f"<tbody>{trs}</tbody></table></div></section>"
    )


def render_article(a: dict) -> str:
    meta = []
    if a.get("author"):
        meta.append(e(a["author"]))
    if a.get("publishAt"):
        meta.append(datetime.fromtimestamp(a["publishAt"], tz=TAIPEI).strftime("%m/%d %H:%M"))
    if a.get("structured_summary"):
        body = ""
        for sec in parse_structured_summary(a["structured_summary"]):
            if sec["header"]:
                body += f'<h4 class="{SECTION_ACCENT.get(sec["header"], "")}">{e(sec["header"])}</h4>'
            body += "<ul>" + "".join(f"<li>{e(it)}</li>" for it in sec["items"]) + "</ul>"
    else:
        body = '<p class="muted">（無摘要，僅提供連結）</p>'
    link = f'<a class="more" href="{e(a["url"])}" target="_blank" rel="noopener">閱讀原文 →</a>' if a.get("url") else ""
    return (
        f'<article class="news"><h3>{e(a.get("title"))}</h3>'
        f'<div class="meta">{" · ".join(meta)}</div>{body}{link}</article>'
    )


def render_digest(d: dict) -> str:
    out = render_fred(d.get("fred", []))
    for sec in d.get("news_sections", []):
        arts = sec.get("articles", [])
        out += (
            f'<section class="card"><h2>{e(sec.get("name"))} <span class="tag">{e(sec.get("source"))}</span>'
            f' <span class="muted small">{len(arts)} 則</span></h2>'
            + "".join(render_article(a) for a in arts)
            + "</section>"
        )
    return out


def date_list(items: list[tuple[str, str]], empty: str) -> str:
    if not items:
        return f'<p class="muted">{empty}</p>'
    return '<ul class="dates">' + "".join(f'<li><a href="{href}">{e(label)}</a></li>' for href, label in items) + "</ul>"


# ---------- 每週研究 ----------

def load_reports() -> list[tuple[str, str]]:
    if not REPORT_DIR.is_dir():
        print(f"⚠️ 找不到 {REPORT_DIR}，每週研究區塊會是空的", file=sys.stderr)
        return []
    return [(f.stem, f.read_text(encoding="utf-8")) for f in sorted(REPORT_DIR.glob("*.md"), reverse=True)]


def render_report(md_text: str) -> str:
    md = markdown.Markdown(extensions=["tables", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2-3"}})
    body = md.convert(md_text)
    toc = f'<details class="card toc"><summary>目錄</summary>{md.toc}</details>' if md.toc_tokens else ""
    # 報告第一行是 H1，標題已由頁面顯示
    body = re.sub(r"^<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    return f'{toc}<div class="card prose">{body}</div>'


def report_teaser(md_text: str) -> str:
    """總覽頁用：抓出每一個「完全符合（N）」的數字。"""
    counts = re.findall(r"^### (.+?)\n.*?^#### 完全符合（(\d+)）", md_text, flags=re.S | re.M)
    return "、".join(f"{e(style.split('（')[0])} {n} 檔完全符合" for style, n in counts)


# ---------- 組裝 ----------

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    shutil.copy(ROOT / "static" / "style.css", OUT_DIR / "style.css")
    shutil.copy(ROOT / "static" / "_headers", OUT_DIR / "_headers")

    digests = load_digests()
    for d in digests:
        write(OUT_DIR / "daily" / f"{d['date']}.html",
              page(f"每日總經 {d['date']}", f"<h1>每日總經摘要 <span class=\"muted\">{e(d['date'])}</span></h1>" + render_digest(d), 1, "daily/index.html"))
    write(OUT_DIR / "daily" / "index.html",
          page("每日總經", "<h1>每日總經摘要</h1>" + date_list([(f"{d['date']}.html", d["date"]) for d in digests], "尚無資料"), 1, "daily/index.html"))

    reports = load_reports()
    for date, md_text in reports:
        write(OUT_DIR / "weekly" / f"{date}.html",
              page(f"每週研究 {date}", f"<h1>每週基本面分析 <span class=\"muted\">{e(date)}</span></h1>" + render_report(md_text), 1, "weekly/index.html"))
    write(OUT_DIR / "weekly" / "index.html",
          page("每週研究", "<h1>每週研究報告</h1>" + date_list([(f"{d}.html", d) for d, _ in reports], "尚無資料"), 1, "weekly/index.html"))

    # 總覽
    tiles = []
    if digests:
        d = digests[0]
        n = sum(len(s.get("articles", [])) for s in d.get("news_sections", []))
        tiles.append(f'<a class="tile" href="daily/{d["date"]}.html"><div class="label">最新每日總經</div>'
                     f'<div class="big">{e(d["date"])}</div><div class="muted">{n} 則新聞 · {len(d.get("fred", []))} 項數據</div></a>')
    if reports:
        date, md_text = reports[0]
        tiles.append(f'<a class="tile" href="weekly/{date}.html"><div class="label">最新每週研究</div>'
                     f'<div class="big">{e(date)}</div><div class="muted">{report_teaser(md_text) or "基本面報告"}</div></a>')
    tiles.append('<div class="tile soon"><div class="label">投資總覽</div><div class="big">建置中</div>'
                 '<div class="muted">Notion 交易紀錄 × 凱基對帳單</div></div>')
    home = '<h1>總覽</h1><div class="tiles">' + "".join(tiles) + "</div>"
    if digests:
        home += f'<h2 class="section-title">今日 FRED 數據</h2>{render_fred(digests[0].get("fred", []))}'
    write(OUT_DIR / "index.html", page("總覽", home, 0, "index.html"))

    print(f"✅ 產生 {len(digests)} 份每日總經、{len(reports)} 份每週研究 → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
