#!/bin/bash
# 部署前的冒煙測試：用 wrangler pages dev 在 CI 裡跑一份完整的網站（本機 D1、真實報價），
# 模擬兩個登入的使用者實際下單，並測投資頁密碼鎖。任何一步失敗就不部署。
set -euo pipefail
BASE=http://localhost:8788
fail() { echo "❌ $*"; exit 1; }
need() { echo "$1" | grep -q "$2" || fail "$3（回應：$(echo "$1" | head -c 300)）"; }
post() { curl -s -X POST -H "Content-Type: application/json" -d "$2" "$BASE$1"; }

# 投資頁：沒登入 → 密碼頁、不能有持股內容
code=$(curl -s -o /tmp/pf.html -w '%{http_code}' "$BASE/portfolio/")
[ "$code" = 401 ] || fail "投資頁沒密碼應該回 401，實際 $code"
grep -q "這一頁需要密碼" /tmp/pf.html || fail "投資頁沒有顯示密碼頁"
grep -q "持股明細" /tmp/pf.html && fail "沒登入就看得到持股內容"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -d "password=wrong" "$BASE/portfolio/__login")
[ "$code" = 401 ] || fail "錯誤密碼應該回 401，實際 $code"
cookie=$(curl -s -D - -o /dev/null -X POST --data-urlencode "password=$SMOKE_PASSWORD" "$BASE/portfolio/__login" | grep -i '^set-cookie:' | sed 's/^[^:]*: //; s/;.*//' | tr -d '\r')
[ -n "$cookie" ] || fail "正確密碼沒有拿到 cookie"
code=$(curl -s -o /tmp/pf.html -w '%{http_code}' -H "Cookie: $cookie" "$BASE/portfolio/")
[ "$code" = 200 ] || fail "帶 cookie 應該看得到投資頁，實際 $code"
grep -q "這一頁需要密碼" /tmp/pf.html && fail "帶 cookie 還是顯示密碼頁"
echo "✅ 投資頁密碼鎖"

# AI 投資顧問：沒登入拿不到頁面、資料與 API；登入後頁面正常、API 會檢查輸入（CI 沒有 AI 金鑰 → 503）
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/portfolio/advisor/"); [ "$code" = 401 ] || fail "顧問頁沒密碼應該回 401，實際 $code"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/portfolio/advisor/holdings.json"); [ "$code" = 401 ] || fail "持股權重沒密碼應該回 401，實際 $code"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/portfolio/advisor/stocks.json"); [ "$code" = 401 ] || fail "顧問資料沒密碼應該回 401，實際 $code"
r=$(curl -s -X POST -H "Content-Type: application/json" -d '{"question":"台積電"}' "$BASE/portfolio/api/advisor"); need "$r" '請重新輸入密碼' "沒登入不能問顧問"
code=$(curl -s -o /tmp/adv.html -w '%{http_code}' -H "Cookie: $cookie" "$BASE/portfolio/advisor/"); [ "$code" = 200 ] || fail "登入後顧問頁應該 200，實際 $code"
grep -q "問顧問" /tmp/adv.html || fail "顧問頁內容不對"
apost() { curl -s -X POST -H "Cookie: $cookie" -H "Content-Type: application/json" -d "$1" "$BASE/portfolio/api/advisor"; }
need "$(apost '{"question":""}')" '請輸入問題' "空白問題應該擋下"
r=$(apost '{"question":"台積電和聯電哪個比較好？"}')
if [ -f site/portfolio/advisor/stocks.json ]; then
  need "$r" 'AI 金鑰還沒設定' "沒有金鑰時應該回清楚的錯誤"
  need "$r" '"found":\["2330","2303"\]' "應該從問題找出台積電與聯電（也代表讀得到顧問資料）"
else
  need "$r" '顧問資料還沒產生' "沒有顧問資料時應該回清楚的錯誤"
fi
echo "✅ AI 投資顧問"

# 模擬交易（ACCESS_DEV_EMAIL=smoke@example.com）
me=$(curl -s "$BASE/api/sim/me"); need "$me" '"cash":1000000' "新帳戶應該有 100 萬"
q=$(curl -s "$BASE/api/sim/quote?code=0050"); need "$q" '"price"' "查不到 0050 報價"
r=$(post /api/sim/order '{"code":"0050","side":"buy","shares":10}'); need "$r" '"ok":true' "買進失敗"
r=$(post /api/sim/order '{"code":"0050","side":"sell","shares":11}'); need "$r" '持股不足' "應該擋下超賣"
r=$(post /api/sim/order '{"code":"0050","side":"sell","shares":4}'); need "$r" '"ok":true' "賣出失敗"
r=$(post /api/sim/order '{"code":"2330","side":"buy","shares":100000}'); need "$r" '現金不足' "應該擋下超買"
r=$(post /api/sim/order '{"code":"0050","side":"buy","shares":-1}'); need "$r" '整數' "應該擋下負股數"
me=$(curl -s "$BASE/api/sim/me"); need "$me" '"shares":6' "持股應該剩 6 股"
need "$(post /api/sim/nickname '{"nickname":"<b>測試</b>"}')" '"ok":true' "改暱稱失敗"
lb=$(curl -s "$BASE/api/sim/leaderboard"); need "$lb" '"me":true' "排行榜沒有自己"
echo "$lb" | grep -q "smoke@example.com" && fail "排行榜洩漏 email"
need "$(post /api/sim/reset '{}')" '"ok":true' "重新開始失敗"
me=$(curl -s "$BASE/api/sim/me"); need "$me" '"resets":1' "重來次數沒有增加"; need "$me" '"holdings":\[\]' "重來後應該沒有持股"
echo "✅ 模擬交易"

# 市場頁：所有登入者都看得到，但不能出現持股提醒
code=$(curl -s -o /tmp/mk.html -w '%{http_code}' "$BASE/market/"); [ "$code" = 200 ] || fail "市場頁應該 200，實際 $code"
grep -q "持股提醒" /tmp/mk.html && fail "市場頁不該有持股提醒"
code=$(curl -s -o /tmp/wh.html -w '%{http_code}' "$BASE/whales/"); [ "$code" = 200 ] || fail "大佬持股頁應該 200，實際 $code"
grep -q "我的持股 × 大佬" /tmp/wh.html && fail "大佬持股頁不該有站長持股"
echo "✅ 市場頁"

# 即時報價 API（來源暫時連不到也要回正常格式）
need "$(curl -s "$BASE/api/live?idx=1&tw=2330,abc")" '"updated"' "即時報價 API 格式不對"
echo "✅ 即時報價"

# 即時快報
n=$(curl -s "$BASE/api/news?cat=tw_stock"); need "$n" '"items":\[{' "即時快報沒有新聞"
need "$(curl -s "$BASE/api/news?cat=nope")" '沒有這個分類' "未知分類應該回錯誤"
echo "✅ 即時快報"
