// LINE 機器人的 webhook：POST /api/line/webhook（LINE 伺服器呼叫，必須略過 Cloudflare Access）。
// - 被邀進群組（join）：記下群組代號；第一個群組自動開通每日一檔推播，其他群組只回說明、不推播
// - 被移出群組（leave）：停用
// - 群組裡有人打「今日一檔」：回覆今天的內容（回覆不算推播額度）
// 每個請求都驗證 LINE 的簽章，假冒的請求一律拒絕。

import { ASK_WORDS, reply, validSignature } from "../../_lib/line.js";

const WELCOME_ON = "大家好！我是 Craig 財經站的每日一檔小幫手 📈\n每天早上 9 點左右會在這裡貼一檔台股介紹（發展歷史、產業位置、未來機會與風險、名詞小辭典與資料來源）。\n想再看一次今天的內容，打「今日一檔」就好。\n※ AI 依公開資料整理，僅供學習研究，不構成投資建議。";
const WELCOME_OFF = "嗨！這個群組還沒有開通每日一檔推播，請聯絡站長。";

async function todayMessages(env, request) {
  try {
    const res = await env.ASSETS.fetch(new Request(new URL("/pick/latest_line.json", request.url)));
    if (!res.ok) return null;
    return (await res.json()).messages || null;
  } catch {
    return null;
  }
}

export async function onRequestPost({ request, env }) {
  const body = await request.text();
  if (!(await validSignature(env.LINE_CHANNEL_SECRET, body, request.headers.get("X-Line-Signature")))) {
    return new Response("bad signature", { status: 401 });
  }
  let events = [];
  try {
    events = JSON.parse(body).events || [];
  } catch {
    return new Response("bad json", { status: 400 });
  }
  const token = env.LINE_CHANNEL_ACCESS_TOKEN;
  for (const ev of events) {
    const gid = ev.source?.type === "group" ? ev.source.groupId : null;
    if (ev.type === "join" && gid && env.DB) {
      const approved = await env.DB.prepare("SELECT COUNT(*) AS n FROM line_groups WHERE approved = 1 AND group_id != ?").bind(gid).first();
      const first = (approved?.n || 0) === 0;
      await env.DB.prepare(`INSERT INTO line_groups (group_id, joined_at, active, approved) VALUES (?, ?, 1, ?)
                            ON CONFLICT(group_id) DO UPDATE SET active = 1`).bind(gid, new Date().toISOString(), first ? 1 : 0).run();
      const row = await env.DB.prepare("SELECT approved FROM line_groups WHERE group_id = ?").bind(gid).first();
      await reply(token, ev.replyToken, [row?.approved ? WELCOME_ON : WELCOME_OFF]);
    } else if (ev.type === "leave" && gid && env.DB) {
      await env.DB.prepare("UPDATE line_groups SET active = 0 WHERE group_id = ?").bind(gid).run();
    } else if (ev.type === "message" && ev.message?.type === "text" && ASK_WORDS.test(ev.message.text.trim())) {
      const allowed = !gid || !env.DB || (await env.DB.prepare("SELECT approved FROM line_groups WHERE group_id = ?").bind(gid).first())?.approved;
      if (!allowed) continue;
      const msgs = await todayMessages(env, request);
      await reply(token, ev.replyToken, msgs || ["今天的每日一檔還沒產生，早上 9 點左右再來看看 🙏"]);
    }
  }
  return new Response("ok");
}

// LINE 後台按「Verify」時會送 POST；GET 只回一句話方便自己檢查網址通不通
export const onRequestGet = () => new Response("Craig 財經站 LINE webhook");
