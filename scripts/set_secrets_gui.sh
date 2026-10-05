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
  printf '%s' "$value" | gh secret set "$n" -R craigshih/finance-hub && echo "$n：✅ 已存進 GitHub Secrets"
  unset value
done
