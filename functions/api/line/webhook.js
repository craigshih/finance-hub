// LINE 機器人的 webhook：POST /api/line/webhook（LINE 伺服器呼叫，必須略過 Cloudflare Access）。
// - 被邀進群組（join）：記下群組代號；第一個群組自動開通每日一檔推播，其他群組只回說明、不推播
// - 被移出群組（leave）：停用
// - 群組裡有人打「今日一檔」：回覆今天的內容（回覆不算推播額度）
// - 「說明」：用法；「大盤」：加權、櫃買與國際指數；「2330」「台積電」：即時報價（整句符合才回，查不到就不出聲）
// - @機器人＋問題（私訊不用 @）：交給專屬投資顧問（訪客版資料，不帶站長持股），每人每天題數有上限
// 每個請求都驗證 LINE 的簽章，假冒的請求一律拒絕。先回 200 給 LINE，AI 慢慢想完再用 reply token 回覆。

import { ALIASES } from "../../_lib/advisor.js";
import { advise, loadData } from "../../_lib/advisor_api.js";
import {
  ASK_WORDS, HELP, HELP_WORDS, MARKET_WORDS, formatAnswer, formatIndices, formatQuote, quoteCodes, reply, startLoading, stripMention,
  validSignature,
} from "../../_lib/line.js";
import { misChannels } from "../../_lib/live.js";
import { lineQuota } from "../../_lib/robot_quota.js";
import { cached, indices, mis } from "../live.js";

const DATA = "/robot/stocks.json";

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

export async function onRequestPost(ctx) {
  const { request, env } = ctx;
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
  const work = Promise.all(events.map((ev) => handleEvent(ev, env, request).catch((exc) => console.error("LINE event", exc))));
  if (ctx.waitUntil) ctx.waitUntil(work);
  else await work;
  return new Response("ok");
}

async function handleEvent(ev, env, request) {
  const token = env.LINE_CHANNEL_ACCESS_TOKEN;
  const gid = ev.source?.type === "group" ? ev.source.groupId : null;
  if (ev.type === "join" && gid && env.DB) {
    const approved = await env.DB.prepare("SELECT COUNT(*) AS n FROM line_groups WHERE approved = 1 AND group_id != ?").bind(gid).first();
    const first = (approved?.n || 0) === 0;
    await env.DB.prepare(`INSERT INTO line_groups (group_id, joined_at, active, approved) VALUES (?, ?, 1, ?)
                          ON CONFLICT(group_id) DO UPDATE SET active = 1`).bind(gid, new Date().toISOString(), first ? 1 : 0).run();
    const row = await env.DB.prepare("SELECT approved FROM line_groups WHERE group_id = ?").bind(gid).first();
    await reply(token, ev.replyToken, row?.approved ? [WELCOME_ON, HELP] : [WELCOME_OFF]);
    return;
  }
  if (ev.type === "leave" && gid && env.DB) {
    await env.DB.prepare("UPDATE line_groups SET active = 0 WHERE group_id = ?").bind(gid).run();
    return;
  }
  if (ev.type !== "message" || ev.message?.type !== "text") return;

  const { text, mentioned } = stripMention(ev.message);
  const direct = ev.source?.type === "user";
  const addressed = mentioned || direct; // 有 @ 機器人或私訊，才會回「查不到」或交給 AI
  const isCommand = ASK_WORDS.test(text) || HELP_WORDS.test(text) || MARKET_WORDS.test(text);
  if (!addressed && !isCommand && text.length > 40) return; // 群組裡的一般聊天，不用查資料庫

  const allowed = !gid || !env.DB || (await env.DB.prepare("SELECT approved FROM line_groups WHERE group_id = ?").bind(gid).first())?.approved;
  if (!allowed) return;
  const send = (texts) => reply(token, ev.replyToken, texts, { quoteToken: ev.message.quoteToken });

  if (ASK_WORDS.test(text)) {
    const msgs = await todayMessages(env, request);
    await reply(token, ev.replyToken, msgs || ["今天的每日一檔還沒產生，早上 9 點左右再來看看 🙏"]);
  } else if (HELP_WORDS.test(text) || (addressed && !text)) {
    await send([HELP]);
  } else if (MARKET_WORDS.test(text)) {
    await send([formatIndices(await cached("idx", indices))]);
  } else {
    const { data } = await loadData(env, request, DATA, null);
    const codes = quoteCodes(text, data?.stocks || {}, ALIASES);
    if (codes) {
      const quotes = await cached(`tw/${[...codes].sort().join(",")}`, () => mis(misChannels(codes)));
      const found = codes.filter((c) => quotes[c]);
      if (found.length) await send([found.map((c) => formatQuote(c, quotes[c], data?.stocks)).join("\n\n")]);
      else if (addressed) await send([`查不到 ${codes.join("、")} 的報價，代號或名稱再確認一下？`]);
    } else if (addressed) {
      await askAdvisor(ev, text, env, request, send);
    }
  }
}

async function askAdvisor(ev, question, env, request, send) {
  const userId = ev.source?.userId;
  if (ev.source?.type === "user") await startLoading(env.LINE_CHANNEL_ACCESS_TOKEN, userId);
  const q = await lineQuota(env, userId);
  const r = await advise({ request, env }, { question }, { dataPath: DATA, holdingsPath: null, guest: true, ...q });
  if (r.blocked) await send([r.blocked]);
  else if (r.status !== 200) await send([`${r.body.error} 🙏`]);
  else await send([formatAnswer(r.body)]);
}

// LINE 後台按「Verify」時會送 POST；GET 只回一句話方便自己檢查網址通不通
export const onRequestGet = () => new Response("Craig 財經站 LINE webhook");
