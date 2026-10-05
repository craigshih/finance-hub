#!/bin/bash
# 用 macOS 彈出視窗輸入金鑰，直接存進 GitHub Secrets（craigshih/finance-hub），不需要在終端機打字。
# 用法：scripts/set_secrets_gui.sh                       # 依序設定三個
#       scripts/set_secrets_gui.sh CLOUDFLARE_ACCOUNT_ID # 只設定指定的名稱
# 輸入的內容不會印在任何地方，也不會存在本機；按「略過」可以跳過某一項。
names=("$@")
[ ${#names[@]} -eq 0 ] && names=(SOURCES_TOKEN CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID)

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
    SOURCES_TOKEN)         hint="請貼上 github_pat_ 開頭的 fine-grained token（只授權 Tim-Lu、investment-team 的 Contents: Read-only）"; hidden=1 ;;
    CLOUDFLARE_API_TOKEN)  hint="請貼上 Cloudflare API token（權限：Account → Cloudflare Pages → Edit）"; hidden=1 ;;
    CLOUDFLARE_ACCOUNT_ID) hint="請貼上 Cloudflare 帳號 ID（32 碼英數字，Dashboard 右側欄）"; hidden=0 ;;
    *)                     hint="請貼上 $n 的值"; hidden=1 ;;
  esac
  value="$(prompt_for "$n" "$hint" "$hidden")"
  value="${value#"${value%%[![:space:]]*}"}"; value="${value%"${value##*[![:space:]]}"}"  # 去掉前後空白
  if [ -z "$value" ]; then
    echo "$n：略過"
    continue
  fi
  if [ "$n" = "SOURCES_TOKEN" ]; then
    # 只印格式與長度，不印內容；並實際試讀兩個來源 repo，失敗就不存
    case $value in
      github_pat_*) kind="fine-grained（github_pat_）" ;;
      ghp_*)        kind="classic（ghp_）" ;;
      *)            kind="不是 GitHub token 的格式（開頭應為 github_pat_）" ;;
    esac
    echo "$n：格式 $kind，長度 ${#value} 字元"
    ok=1
    for repo in Tim-Lu investment-team; do
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
  printf '%s' "$value" | gh secret set "$n" -R craigshih/finance-hub && echo "$n：✅ 已存進 GitHub Secrets"
  unset value
done
