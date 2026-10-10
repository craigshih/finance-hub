// AI 投資機器人（訪客版）：POST /robot/api/advisor
// 跟站長版同一套分析，但不帶持股、不寫入每日追蹤清單，並限制每人每天的題數（Groq 免費額度有限）。

import { handleAdvisor } from "../../_lib/advisor_api.js";
import { accessEmail } from "../../_lib/auth.js";
import { hmacHex } from "../../_lib/session.js";
import { DAILY_LIMIT, GLOBAL_DAILY_LIMIT } from "../../_lib/robot.js";

const taipeiDay = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);

async function quota(request, env) {
  if (!env.DB) return null;
  const who = (await accessEmail(request, env)) || request.headers.get("CF-Connecting-IP") || "anon";
  const id = (await hmacHex(env.SESSION_SECRET, `robot:${who}`)).slice(0, 24); // 不存 email 本身
  const day = taipeiDay();
  const total = await env.DB.prepare("SELECT COALESCE(SUM(n), 0) AS n FROM robot_usage WHERE day = ?").bind(day).first();
  if ((total?.n || 0) >= GLOBAL_DAILY_LIMIT) return Response.json({ error: "今天機器人的總題數已用完，明天再來" }, { status: 429 });
  const row = await env.DB.prepare(
    "INSERT INTO robot_usage (day, who, n) VALUES (?, ?, 1) ON CONFLICT(day, who) DO UPDATE SET n = n + 1 RETURNING n",
  ).bind(day, id).first();
  if ((row?.n || 0) > DAILY_LIMIT) return Response.json({ error: `每人每天最多 ${DAILY_LIMIT} 題，明天再來` }, { status: 429 });
  return null;
}

export const onRequestPost = (ctx) => handleAdvisor(ctx, {
  dataPath: "/robot/stocks.json", holdingsPath: null, guest: true, beforeAsk: () => quota(ctx.request, ctx.env),
});
