// AI 投資機器人（訪客版）：/robot/ 底下要先輸入通關語（預設「i need investment robot」）。
// 這裡只放機器人本身與不含持股的股票資料；站長持股仍在 /portfolio/，要另外的密碼。

import { getCookie } from "../_lib/session.js";
import { ROBOT_COOKIE, ROBOT_DAYS, makeRobotToken, phraseMatches, validRobotToken } from "../_lib/robot.js";

const NO_STORE = "private, no-store";

function gatePage(message, status = 401) {
  const note = message ? `<p class="login-msg">${message}</p>` : "";
  const html = `<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>AI 投資機器人 · Craig 財經站</title>
<link rel="stylesheet" href="/style.css"></head>
<body>
<header class="top"><div class="wrap"><a class="brand" href="/"><span class="mark">C</span><span class="brand-text">Craig 財經站</span></a>
<nav><a href="/">總覽</a><a href="/market/">台股</a><a href="/us/">美股</a><a href="/news/">即時快報</a><a href="/daily/">每日總經</a><a href="/weekly/">每週研究</a><a href="/supply/">供應鏈</a><a href="/whales/">大佬持股</a><a href="/sim/">模擬交易</a><a class="on" href="/robot/">AI 機器人</a><a href="/portfolio/">投資</a></nav></div></header>
<section class="hero"><div class="wrap"><div class="kicker">AI 投資機器人</div><h1>想跟 AI 討論股票？</h1>
<p class="hero-sub">輸入通關語就能使用：籌碼 × 財報 × 輿情，風控派與回測派先辯論，再給融合後的看法。</p></div></section>
<main class="wrap"><form class="login" method="post" action="/robot/__enter">
<label for="phrase">通關語</label>
<input id="phrase" name="phrase" type="text" autocomplete="off" placeholder="例如：i need investment robot" required autofocus>
<button type="submit">開始使用</button>${note}
<p class="muted">機器人只用公開市場資料，不會看到站長的持股；內容是 AI 研究意見，不是投資建議。</p></form></main>
</body></html>`;
  return new Response(html, { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": NO_STORE } });
}

export async function onRequest({ request, env, next }) {
  const { pathname } = new URL(request.url);
  if (!env.SESSION_SECRET) return gatePage("機器人還沒設定好，暫時無法使用。", 503);
  const cookieAttrs = "Path=/robot; HttpOnly; Secure; SameSite=Lax";

  if (pathname === "/robot/__enter") {
    if (request.method !== "POST") return Response.redirect(new URL("/robot/", request.url), 303);
    const form = await request.formData();
    if (phraseMatches(env, form.get("phrase"))) {
      return new Response(null, {
        status: 303,
        headers: { Location: "/robot/", "Cache-Control": NO_STORE,
                   "Set-Cookie": `${ROBOT_COOKIE}=${await makeRobotToken(env)}; ${cookieAttrs}; Max-Age=${ROBOT_DAYS * 86400}` },
      });
    }
    await new Promise((r) => setTimeout(r, 800));
    return gatePage("通關語不對，再試一次");
  }

  if (await validRobotToken(env, getCookie(request, ROBOT_COOKIE))) {
    const res = await next();
    const out = new Response(res.body, res);
    out.headers.set("Cache-Control", NO_STORE);
    return out;
  }
  if (pathname.startsWith("/robot/api/")) return Response.json({ error: "請先輸入通關語" }, { status: 401 });
  return gatePage("");
}
