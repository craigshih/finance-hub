# Craig 財經站

把各個自動化 repo 的產出整合成一個私人網站，部署在 Cloudflare Pages，並用 Cloudflare Access 限制只有自己的 email 能登入。

## 資料來源

| 區塊 | 來源 | 檔案 |
|---|---|---|
| 每日總經 | `craigshih/Tim-Lu` | `data/digests/{date}.json` |
| 每週研究 | `craigshih/investment-team` | `data/reports/{date}.md` |
| 投資總覽 | Notion「股票交易管理」（股票代號／股票交易紀錄／配息紀錄／股價紀錄） | Notion API，build 時即時讀取，不存檔 |
| 對帳 | `craigshih/craig-stock-trade-report`（本機資料夾 ~/kgi-trade-report） | `data/statements/{YYYY-MM}.json` |

`build.py` 讀上面這些來源，輸出純靜態 HTML 到 `site/`。網站壞掉不影響原本寄信的流程；Notion 讀不到時其他頁面照常產生。

投資總覽直接讀 Notion「股票代號」主檔的公式結果（庫存股數、均價、市值、損益），不自己重算。對帳（`portfolio.reconcile`）只比對對帳單有涵蓋的月份：交易日、代號、買賣別、股數相同且單價差 ≤ 0.01 才算相符；Notion 標記「分割調整」的紀錄不參與比對。持股數字只會出現在網頁上，build log 只印筆數。

## 運作

`.github/workflows/build.yml` 每天台北時間 22:00（Notion 收盤價寫入之後）執行：checkout 三個來源 repo → `python build.py` → 部署到 Cloudflare Pages 專案 `craig-finance`。也可以在 Actions 頁面手動觸發。

## 需要的 GitHub Secrets

| Secret | 說明 |
|---|---|
| `SOURCES_TOKEN` | GitHub fine-grained token，只授權 `Tim-Lu`、`investment-team`、`craig-stock-trade-report` 的 **Contents: Read-only** |
| `NOTION_TOKEN` | Notion internal integration，Capabilities 只勾 **Read content**，並把「股票交易管理」頁面分享給它 |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token，權限 **Account → Cloudflare Pages → Edit** |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 帳號 ID（Dashboard 右側欄） |

## 隱私

- **一定要先設定 Cloudflare Access 再放持股資料。** Pages 部署完預設是公開網址。
- Access 設定：Zero Trust → Access → Applications → Self-hosted，網域填 `craig-finance.pages.dev`（以及 `*.craig-finance.pages.dev`，涵蓋每次部署的預覽網址），Policy 選 Allow、Include → Emails → 自己的 Gmail。
- `_headers` 加了 `X-Robots-Tag: noindex`，避免被搜尋引擎收錄。

## 本機預覽

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
SOURCES_DIR=/path/to/sources .venv/bin/python build.py   # sources/ 底下放 tim-lu、investment-team
python3 -m http.server 8765 -d site
```
