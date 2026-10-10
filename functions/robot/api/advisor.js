// 專屬投資顧問（訪客版）：POST /robot/api/advisor
// 跟站長版同一套分析，但不帶持股、不寫入每日追蹤清單，並有每人每天題數與全體訪客 token 上限（見 _lib/robot.js）。

import { handleAdvisor } from "../../_lib/advisor_api.js";
import { accessEmail } from "../../_lib/auth.js";
import { hmacHex } from "../../_lib/session.js";
import { TOKENS_ROW, guestBlocked } from "../../_lib/robot.js";

const taipeiDay = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);

async function visitorId(request, env) {
  const who = (await accessEmail(request, env)) || request.headers.get("CF-Connecting-IP") || "anon";
  return (await hmacHex(env.SESSION_SECRET || "robot", `robot:${who}`)).slice(0, 24); // 不存 email 本身
}

export async function onRequestPost(ctx) {
  const { request, env } = ctx;
  const day = taipeiDay();
  const id = await visitorId(request, env);
  const usage = async () => {
    const { results } = await env.DB.prepare("SELECT who, n FROM robot_usage WHERE day = ? AND who IN (?, ?)").bind(day, id, TOKENS_ROW).all();
    const get = (w) => results.find((r) => r.who === w)?.n || 0;
    return { mine: get(id), tokens: get(TOKENS_ROW) };
  };
  const bump = (who, by) => env.DB.prepare(
    "INSERT INTO robot_usage (day, who, n) VALUES (?, ?, ?) ON CONFLICT(day, who) DO UPDATE SET n = n + excluded.n",
  ).bind(day, who, by).run();

  return handleAdvisor(ctx, {
    dataPath: "/robot/stocks.json", holdingsPath: null, guest: true,
    beforeAsk: async () => {
      if (!env.DB) return null;
      const msg = guestBlocked(await usage(), env);
      if (msg) return Response.json({ error: msg }, { status: 429 });
      await bump(id, 1);
      return null;
    },
    afterAsk: async (tokens) => {
      if (env.DB && tokens) await bump(TOKENS_ROW, tokens);
    },
  });
}
