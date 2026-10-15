// 訪客版（/robot/）的用量：每人每天題數＋全體訪客每天 token 上限（規則在 robot.js）。顧問與選股共用同一份額度。
import { accessEmail } from "./auth.js";
import { hmacHex } from "./session.js";
import { TOKENS_ROW, guestBlocked } from "./robot.js";

const taipeiDay = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);

export async function guestQuota(request, env) {
  const day = taipeiDay();
  const who = (await accessEmail(request, env)) || request.headers.get("CF-Connecting-IP") || "anon";
  const id = (await hmacHex(env.SESSION_SECRET || "robot", `robot:${who}`)).slice(0, 24); // 不存 email 本身
  const bump = (w, by) => env.DB.prepare(
    "INSERT INTO robot_usage (day, who, n) VALUES (?, ?, ?) ON CONFLICT(day, who) DO UPDATE SET n = n + excluded.n",
  ).bind(day, w, by).run();
  return {
    beforeAsk: async () => {
      if (!env.DB) return null;
      const { results } = await env.DB.prepare("SELECT who, n FROM robot_usage WHERE day = ? AND who IN (?, ?)").bind(day, id, TOKENS_ROW).all();
      const get = (w) => results.find((r) => r.who === w)?.n || 0;
      const msg = guestBlocked({ mine: get(id), tokens: get(TOKENS_ROW) }, env);
      if (msg) return Response.json({ error: msg }, { status: 429 });
      await bump(id, 1);
      return null;
    },
    afterAsk: async (tokens) => {
      if (env.DB && tokens) await bump(TOKENS_ROW, tokens);
    },
  };
}
