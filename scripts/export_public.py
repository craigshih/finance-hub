"""匯出給朋友用的「乾淨版」：程式碼都給，但拿掉站長的持股、交易、對帳相關部分，git 歷史也重新開始。

用法：.venv/bin/python scripts/export_public.py /path/to/輸出資料夾
輸出資料夾會被清空重建；最後會掃一次敏感字串，有漏網之魚就失敗、不產生 commit。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 整個拿掉的檔案（持股來源設定、金鑰設定流程、這支腳本本身、建站狀態）
REMOVE = ["scripts/set_secrets_gui.sh", "scripts/export_public.py", "data/state"]

PORTFOLIO_STUB = '''"""公開版：不含持股、交易與對帳功能。

原版這裡會從私人資料庫讀持股與交易紀錄；公開版一律回報「讀不到」，
build.py 會照常產生其他頁面，投資總覽頁顯示說明文字。想接自己的持股，照下面的介面實作即可。
"""
from pathlib import Path


class NotionUnavailable(Exception):
    pass


def load_notion() -> dict:
    """回傳 {"tickers": [...], "trades": [...]}；公開版不提供。"""
    raise NotionUnavailable("公開版不含持股功能")


def summarize(nd: dict) -> dict:
    raise NotionUnavailable("公開版不含持股功能")


def load_statements(statement_dir: Path) -> list[dict]:
    return []


def reconcile(statements: list[dict], notion_trades: list[dict], tickers: list[dict]) -> dict | None:
    return None


def issue_count(rc: dict | None) -> int:
    return 0
'''

# (檔案, 原文, 取代) —— 原文找不到就失敗，避免原版改了以後默默漏掉
REPLACE = [
    (".github/workflows/build.yml",
     re.compile(r"\n      # 對帳用；.*?sparse-checkout: data/statements\n", re.S), "\n"),
    (".github/workflows/build.yml", re.compile(r'ACCESS_TEAM_DOMAIN = "[^"]+"'), 'ACCESS_TEAM_DOMAIN = "你的團隊.cloudflareaccess.com"'),
    (".github/workflows/build.yml", re.compile(r'ACCESS_AUD = "[0-9a-f]+"'), 'ACCESS_AUD = "你的 Access 應用程式 AUD"'),
    (".github/workflows/build.yml", re.compile(r"kgi-trade-report 晚上 8～9 點把收盤價寫進 Notion 之後"), "收盤資料都齊了之後"),
    ("build.py", re.compile(r"凱基"), "券商"),
    ("build.py", re.compile(r"craig-stock-trade-report"), "對帳單 repo"),
    ("build.py", re.compile(r"kgi-trade-report"), "trade-report"),
]

# 匯出後全文掃描：出現任何一個就失敗
LEAKS = [
    r"[0-9a-f]{8}-?b27a-?[0-9a-f]{4}",   # Notion 資料庫 ID
    # 「凱基」本身是上市公司名稱，市場資料裡會出現，所以只抓對帳相關字眼
    r"凱基(對帳|證券帳)", r"(?i)kgi", r"craig-stock-trade-report", r"quiet-cell", r"ffa5bda759",
    r"@gmail\.com", r"宥丞", r"shiyoucheng", r"github_pat_[A-Za-z0-9]",
]

README = """# Craig 財經站（公開版）

台股、美股資訊整理網站的原始碼：每日一檔、台股收盤（指數、法人、族群、市場寬度、RRG）、美股、
供應鏈地圖、大佬 13F 持股、模擬交易、AI 投資顧問與選股機器人。部署在 Cloudflare Pages（靜態頁 + Pages Functions + D1）。

這份是「公開版」：拿掉了站長個人的持股、交易紀錄與對帳功能（`portfolio.py` 換成空殼），其餘程式都在。

## 直接拿資料（最簡單）

不想自己建站的話，正式站有公開 JSON（每天收盤後、早上 9 點左右更新）：

| 網址 | 內容 |
|---|---|
| `https://craig-finance.pages.dev/feed/index.json` | 說明與免責聲明 |
| `https://craig-finance.pages.dev/feed/daily-pick.json` | 今日的每日一檔；`text` 是排好版的純文字，每則都在 Discord 2000 字上限內 |
| `https://craig-finance.pages.dev/feed/daily-pick-archive.json` | 最近 60 天的每日一檔清單 |
| `https://craig-finance.pages.dev/feed/market.json` | 台股收盤：`summary` 一句話總結，加上指數、三大法人、族群、強勢股、注意處置股、除權息、估值、期貨籌碼 |
| `https://craig-finance.pages.dev/feed/us.json` | 美股指數、類股 ETF、權值股、SEC 最新申報 |

Discord 範例（discord.py，每天 9:10 把每日一檔貼到頻道）：

```python
import aiohttp, discord
from discord.ext import tasks
from datetime import time, timezone, timedelta

CHANNEL_ID = 123456789  # 你的頻道
client = discord.Client(intents=discord.Intents.default())

@tasks.loop(time=time(9, 10, tzinfo=timezone(timedelta(hours=8))))
async def daily_pick():
    async with aiohttp.ClientSession() as s:
        d = await (await s.get("https://craig-finance.pages.dev/feed/daily-pick.json")).json()
    ch = client.get_channel(CHANNEL_ID)
    for msg in d["text"]:
        await ch.send(msg)

@client.event
async def on_ready():
    daily_pick.start()

client.run("你的 bot token")
```

## 自己建一份

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python market.py && .venv/bin/python us.py      # 抓資料（其他資料腳本見 .github/workflows/build.yml）
.venv/bin/python build.py                                # 輸出到 site/
npm install && npx wrangler pages dev site               # 本機預覽（含 Functions）
```

- 部署流程在 `.github/workflows/`，需要的 secrets：`CLOUDFLARE_API_TOKEN`、`GROQ_API_KEY`（AI 文字）、`SESSION_SECRET`、
  `PORTFOLIO_PASSWORD`（顧問頁密碼）；每日一檔寄信另需 `GMAIL_USER`、`GMAIL_APP_PASSWORD`、`MAIL_TO`，LINE 推播需 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`。
- workflow 裡 checkout `craigshih/Tim-Lu`（每日總經）與 `craigshih/investment-team`（每週研究）兩個私人 repo，沒有權限時那兩區會是空的，其他照常。
- `build.yml` 產生 wrangler.toml 的地方，`ACCESS_TEAM_DOMAIN`、`ACCESS_AUD` 要換成你自己的 Cloudflare Access 設定。
- 測試：`node --test tests/*.test.js`。

## 資料來源與聲明

證交所、櫃買中心、期交所 OpenAPI，Yahoo Finance、SEC EDGAR、維基百科、鉅亨網。不爬取 robots.txt 禁止的網站。
AI 產生的文字僅供學習研究，不構成投資建議。
"""


def main(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    # 只匯出目前 commit 的檔案（不含 .git、site、sources、data/advisor 等沒進版控的東西）
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)

    for rel in REMOVE:
        p = dest / rel
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    (dest / "portfolio.py").write_text(PORTFOLIO_STUB, encoding="utf-8")
    (dest / "README.md").write_text(README, encoding="utf-8")
    for rel, pat, rep in REPLACE:
        f = dest / rel
        text = f.read_text(encoding="utf-8")
        new, n = pat.subn(rep, text)
        if not n:
            sys.exit(f"❌ {rel} 找不到要替換的內容：{pat.pattern[:60]}（原版改過了？請更新 REPLACE）")
        f.write_text(new, encoding="utf-8")

    bad = []
    for f in dest.rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="ignore")
            bad += [f"{f.relative_to(dest)}：{p}" for p in LEAKS if re.search(p, text)]
    if bad:
        sys.exit("❌ 匯出內容還有敏感字串：\n" + "\n".join(bad))
    print(f"✅ 匯出完成：{dest}（{sum(1 for f in dest.rglob('*') if f.is_file())} 個檔案）")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).expanduser().resolve())
