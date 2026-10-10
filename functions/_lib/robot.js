// AI 投資機器人（訪客版）的通關語：輸入「i need investment robot」之類的句子就能進 /robot/。
// 跟投資頁密碼完全分開：通關後只能用機器人討論股票，看不到任何站長持股。

import { hmacHex, safeEqual } from "./session.js";

export const ROBOT_COOKIE = "rb_session";
export const ROBOT_DAYS = 30;
export const DEFAULT_PHRASE = "i need investment robot";
export const DAILY_LIMIT = 20;       // 每位訪客每天最多問幾題（Groq 免費額度有限）
export const GLOBAL_DAILY_LIMIT = 300;

// 不分大小寫、忽略標點與多餘空白："I need  investment robot!" 也算
export function normalizePhrase(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9一-鿿]+/g, " ").trim();
}

export function phraseMatches(env, input) {
  return normalizePhrase(input) === normalizePhrase(env.ROBOT_PHRASE || DEFAULT_PHRASE);
}

const key = (env) => `${env.SESSION_SECRET}|robot|${normalizePhrase(env.ROBOT_PHRASE || DEFAULT_PHRASE)}`;

export async function makeRobotToken(env, now = Date.now()) {
  const exp = now + ROBOT_DAYS * 86400_000;
  return `${exp}.${await hmacHex(key(env), `rb:${exp}`)}`;
}

export async function validRobotToken(env, token, now = Date.now()) {
  if (!token || !env.SESSION_SECRET) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || !(Number(exp) > now)) return false;
  return safeEqual(sig, await hmacHex(key(env), `rb:${exp}`));
}
