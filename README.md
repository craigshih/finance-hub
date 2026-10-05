# Craig 財經站

把各個自動化 repo 的產出整合成一個私人網站，部署在 Cloudflare Pages，並用 Cloudflare Access 限制只有自己的 email 能登入。

## 資料來源

| 區塊 | 來源 | 檔案 |
|---|---|---|
| 每日總經 | `craigshih/Tim-Lu` | `data/digests/{date}.json` |
| 每週研究 | `craigshih/investment-team` | `data/reports/{date}.md` |
| 投資總覽（規劃中） | Notion「股票交易管理」＋ `craig-stock-trade-report` 凱基對帳單 | — |

`build.py` 只讀上面這些檔案、不打外部 API，輸出純靜態 HTML 到 `site/`。網站壞掉不影響原本寄信的流程。

## 運作

`.github/workflows/build.yml` 每天台北時間 15:00（台股收盤後）執行：checkout 兩個來源 repo → `python build.py` → 部署到 Cloudflare Pages 專案 `craig-finance`。也可以在 Actions 頁面手動觸發。

## 需要的 GitHub Secrets

| Secret | 說明 |
|---|---|
| `SOURCES_TOKEN` | GitHub fine-grained token，只授權 `Tim-Lu`、`investment-team` 兩個 repo 的 **Contents: Read-only** |
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
