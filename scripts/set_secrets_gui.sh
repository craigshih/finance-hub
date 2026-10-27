#!/bin/bash
# 用 macOS 彈出視窗輸入金鑰，直接存進 GitHub Secrets（craigshih/finance-hub），不需要在終端機打字。
# 用法：scripts/set_secrets_gui.sh                       # 依序設定全部
#       scripts/set_secrets_gui.sh CLOUDFLARE_ACCOUNT_ID # 只設定指定的名稱
#       CLIPBOARD=1 scripts/set_secrets_gui.sh GH_DISPATCH_TOKEN  # 不跳視窗，直接用剪貼簿裡的值（存完會清空剪貼簿）
# 輸入的內容不會印在任何地方，也不會存在本機；按「略過」可以跳過某一項。
names=("$@")
[ ${#names[@]} -eq 0 ] && names=(SOURCES_TOKEN CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID NOTION_TOKEN PORTFOLIO_PASSWORD)

prompt_for() {
  osascript - "$1" "$2" "$3" <<'APPLESCRIPT' 2>/dev/null
on run argv
  set theName to item 1 of argv
  set theHint to item 2 of argv
  set isHidden to (item 3 of argv) is "1"
  set msg to "財經站金鑰設定" & return & return & theName & return & theHint
  if isHidden then
    set r to display dialog msg default answer "" with hidden answer buttons {"略過", "儲存"} default button "儲存" with title "finance-hub"
  else
    set r to display dialog msg default answer "" buttons {"略過", "儲存"} default button "儲存" with title "finance-hub"
  end if
  if button returned of r is "略過" then return ""
  return text returned of r
end run
APPLESCRIPT
}

for n in "${names[@]}"; do
  case $n in
    SOURCES_TOKEN)         hint="請貼上 github_pat_ 開頭的 fine-grained token（只授權 Tim-Lu、investment-team、craig-stock-trade-report 的 Contents: Read-only）"; hidden=1 ;;
    NOTION_TOKEN)          hint="請貼上唯讀 Notion integration 的 Internal Integration Secret（ntn_ 開頭）"; hidden=1 ;;
    PORTFOLIO_PASSWORD)    hint="設定投資頁的密碼（至少 10 個字元；網站對所有 email 開放，請不要用跟其他服務一樣的密碼）"; hidden=1 ;;
    CLOUDFLARE_API_TOKEN)  hint="請貼上 Cloudflare API token（權限：Account → Cloudflare Pages → Edit、Account → D1 → Edit）"; hidden=1 ;;
    CLOUDFLARE_ACCOUNT_ID) hint="請貼上 Cloudflare 帳號 ID（32 碼英數字，Dashboard 右側欄）"; hidden=0 ;;
    GH_DISPATCH_TOKEN)     hint="請貼上 github_pat_ 開頭的 fine-grained token（授權 finance-hub、craig-stock-trade-report，Actions: Read and write）。存檔前會先測試"; hidden=1 ;;
    *)                     hint="請貼上 $n 的值"; hidden=1 ;;
  esac
  if [ "${CLIPBOARD:-}" = 1 ]; then
    value="$(pbpaste)"
    echo "$n：讀取剪貼簿（${#value} 字）"
  else
    value="$(prompt_for "$n" "$hint" "$hidden")"
  fi
  value="${value#"${value%%[![:space:]]*}"}"; value="${value%"${value##*[![:space:]]}"}"  # 去掉前後空白
  if [ -z "$value" ]; then
    echo "$n：略過"
    continue
  fi
  if [ "$n" = "SOURCES_TOKEN" ]; then
    # 只印格式與長度，不印內容；並實際試讀三個來源 repo，失敗就不存
    case $value in
      github_pat_*) kind="fine-grained（github_pat_）" ;;
      ghp_*)        kind="classic（ghp_）" ;;
      *)            kind="不是 GitHub token 的格式（開頭應為 github_pat_）" ;;
    esac
    echo "$n：格式 $kind，長度 ${#value} 字元"
    ok=1
    for repo in Tim-Lu investment-team craig-stock-trade-report; do
      code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $value" "https://api.github.com/repos/craigshih/$repo")
      case $code in
        200) echo "  $repo：✅ 讀得到" ;;
        401) echo "  $repo：❌ 401 token 無效（貼錯、不完整、或已刪除）"; ok=0 ;;
        404) echo "  $repo：❌ 404 token 有效但沒有授權這個 repo"; ok=0 ;;
        *)   echo "  $repo：❌ HTTP $code"; ok=0 ;;
      esac
    done
    if [ $ok -eq 0 ]; then echo "$n：未儲存，請修正後重試"; unset value; continue; fi
  fi
  if [ "$n" = "PORTFOLIO_PASSWORD" ]; then
    if [ ${#value} -lt 10 ]; then echo "$n：❌ 太短（${#value} 字元），至少 10 個字元；未儲存"; unset value; continue; fi
    again="$(prompt_for "$n" "請再輸入一次確認" 1)"
    again="${again#"${again%%[![:space:]]*}"}"; again="${again%"${again##*[![:space:]]}"}"
    if [ "$value" != "$again" ]; then echo "$n：❌ 兩次輸入不一樣；未儲存"; unset value again; continue; fi
    unset again
    # 換密碼時一起換掉 cookie 簽章金鑰，所有已登入的裝置都要重新輸入密碼
    openssl rand -hex 32 | tr -d '\n' | gh secret set SESSION_SECRET -R craigshih/finance-hub && echo "SESSION_SECRET：✅ 已自動產生"
  fi
  if [ "$n" = "NOTION_TOKEN" ]; then
    # 只印格式與長度，不印內容
    case $value in
      ntn_*|secret_*) kind="Notion integration secret（${value%%_*}_）" ;;
      *)              kind="不是 Notion integration secret 的格式（開頭應為 ntn_）" ;;
    esac
    echo "$n：格式 $kind，長度 ${#value} 字元"
    # 實際讀一次「股票代號」資料庫，確認 token 有效而且有分享到「股票交易管理」
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $value" -H "Notion-Version: 2022-06-28" \
      "https://api.notion.com/v1/databases/ebe40356-b27a-8346-ba19-816b30b76fdf")
    case $code in
      200) echo "$n：✅ 讀得到「股票代號」資料庫" ;;
      401) echo "$n：❌ 401 token 無效（貼錯或不完整）"; echo "$n：未儲存"; unset value; continue ;;
      404) echo "$n：❌ 404 token 有效，但「股票交易管理」頁面還沒分享給這個 integration"; echo "$n：未儲存"; unset value; continue ;;
      *)   echo "$n：❌ HTTP $code"; echo "$n：未儲存"; unset value; continue ;;
    esac
  fi
  # 能驗證的就先實際測一次，不對就不存（隱藏輸入看不到自己貼了什麼，最常見的是少貼一段或貼了兩次）
  if [ "$n" = "GH_DISPATCH_TOKEN" ]; then
    ok=1
    for target in craigshih/finance-hub/daily_pick.yml craigshih/craig-stock-trade-report/daily-price-update.yml; do
      code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $value" "https://api.github.com/repos/${target%/*}/actions/workflows/${target##*/}")
      case $code in
        200) echo "  ${target%/*}：✅ 讀得到" ;;
        401) echo "  ${target%/*}：❌ 401 token 無效（貼錯、不完整、或貼了兩次；長度 ${#value} 字，正常約 93 字）"; ok=0 ;;
        403|404) echo "  ${target%/*}：❌ $code 這把 token 沒有授權這個 repo，或 Actions 權限不是 Read and write"; ok=0 ;;
        *) echo "  ${target%/*}：❌ HTTP $code"; ok=0 ;;
      esac
    done
    [ "$ok" = 1 ] || { echo "$n：未儲存"; unset value; continue; }
  fi
  if [ "$n" = "DISCORD_WEBHOOK_URL" ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' "$value")
    [ "$code" = 200 ] || { echo "$n：❌ webhook 網址測試失敗（HTTP $code），未儲存"; unset value; continue; }
    echo "  webhook：✅ 有效"
  fi
  printf '%s' "$value" | gh secret set "$n" -R "${TARGET_REPO:-craigshih/finance-hub}" && echo "$n：✅ 已存進 ${TARGET_REPO:-craigshih/finance-hub} 的 GitHub Secrets"
  [ "${CLIPBOARD:-}" = 1 ] && printf '' | pbcopy  # 金鑰不要留在剪貼簿
  unset value
done
