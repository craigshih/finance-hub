// LINE webhook 端到端：假的 LINE、證交所、Yahoo、Groq、D1、靜態檔，確認每種訊息回什麼、什麼時候不出聲
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { beforeEach, test } from "node:test";

import { onRequestPost } from "../functions/api/line/webhook.js";

const SECRET = "test-secret";
const DATA = {
  generated_at: "2026-10-19T00:30:00Z", price_codes: ["2330"],
  stocks: { "2330": { code: "2330", name: "台積電", market: "上市" }, "2317": { code: "2317", name: "鴻海", market: "上市" } },
};
let replies, groqCalls, usage, approved;

globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
globalThis.fetch = async (input, init = {}) => {
  const url = String(input.url || input);
  if (url.includes("api.line.me/v2/bot/message/reply")) {
    replies.push(JSON.parse(init.body));
    return new Response("{}");
  }
  if (url.includes("api.line.me")) return new Response("{}");
  if (url.includes("mis.twse.com.tw")) {
    const arr = [];
    if (url.includes("tse_2330.tw")) arr.push({ c: "2330", n: "台積電", z: "1085", y: "1070", o: "1070", h: "1090", l: "1065", v: "23456", ex: "tse", d: "20261019", t: "10:31:12" });
    if (url.includes("tse_t00.tw")) arr.push({ c: "t00", z: "23456.78", y: "23333.38", ex: "tse", d: "20261019", t: "13:30:00" });
    return Response.json({ msgArray: arr });
  }
  if (url.includes("finance.yahoo.com")) return Response.json({ spark: { result: [] } });
  if (url.includes("api.groq.com")) {
    groqCalls.push(JSON.parse(init.body));
    const content = JSON.stringify({ mode: "coach", headline: "本益比是股價除以每股盈餘", coach: "用來看股價貴不貴。", follow_ups: [] });
    return Response.json({ choices: [{ message: { content } }], usage: { total_tokens: 900 } });
  }
  return new Response("", { status: 404 }); // 新聞、PTT 抓不到也要能回答
};

const db = {
  prepare(sql) {
    const stmt = { args: [], bind(...a) { stmt.args = a; return stmt; } };
    stmt.first = async () => (sql.includes("SELECT approved") ? { approved } : { n: 1 });
    stmt.all = async () => ({ results: usage });
    stmt.run = async () => ({});
    return stmt;
  },
  batch: async () => [],
};
const env = {
  LINE_CHANNEL_SECRET: SECRET, LINE_CHANNEL_ACCESS_TOKEN: "tok", GROQ_API_KEY: "k", SESSION_SECRET: "s", DB: db,
  ASSETS: { fetch: async (req) => (new URL(req.url).pathname === "/robot/stocks.json"
    ? Response.json(DATA) : new Response("not found", { status: 404 })) },
};

async function send(message, source = { type: "group", groupId: "G1", userId: "U1" }) {
  const body = JSON.stringify({ events: [{ type: "message", replyToken: "r", source, message: { type: "text", quoteToken: "qt", ...message } }] });
  const sig = createHmac("sha256", SECRET).update(body).digest("base64");
  const res = await onRequestPost({ request: new Request("https://x.test/api/line/webhook", { method: "POST", body, headers: { "X-Line-Signature": sig } }), env });
  assert.equal(res.status, 200);
  return replies.map((r) => r.messages.map((m) => m.text).join("\n---\n"));
}
const atBot = (q) => ({ text: `@小幫手 ${q}`, mention: { mentionees: [{ index: 0, length: 4, isSelf: true }] } });

beforeEach(() => { replies = []; groqCalls = []; usage = []; approved = 1; });

test("群組打代號或名稱：回即時報價，並引用原訊息", async () => {
  const [out] = await send({ text: "台積電" });
  assert.match(out, /📈 台積電 2330（上市）\n1,085 元　▲15（\+1.40%）/);
  assert.equal(replies[0].messages[0].quoteToken, "qt");
});

test("群組一般聊天、查不到的數字：不出聲；@ 機器人才回查不到", async () => {
  assert.deepEqual(await send({ text: "晚上吃什麼" }), []);
  assert.deepEqual(await send({ text: "1234" }), []);
  assert.match((await send(atBot("1234")))[0], /查不到 1234 的報價/);
});

test("大盤、說明、只 @ 不打字", async () => {
  assert.match((await send({ text: "大盤" }))[0], /台股加權　23,456.78　▲0.53%/);
  replies = [];
  assert.match((await send({ text: "說明" }))[0], /查股價/);
  replies = [];
  assert.match((await send(atBot("")))[0], /查股價/);
});

test("@機器人問問題：交給 AI，回答有免責聲明；沒 @ 不會花 AI 額度", async () => {
  const [out] = await send(atBot("什麼是本益比？"));
  assert.match(out, /💬 本益比是股價除以每股盈餘\n\n用來看股價貴不貴。/);
  assert.match(out, /不構成投資建議/);
  assert.equal(groqCalls.length, 1);
  assert.match(groqCalls[0].messages.at(-1).content, /問題：什麼是本益比？$/);
  replies = [];
  assert.deepEqual(await send({ text: "什麼是本益比？" }), []);
  assert.equal(groqCalls.length, 1);
});

test("私訊不用 @ 就能問", async () => {
  const [out] = await send({ text: "什麼是本益比" }, { type: "user", userId: "U2" });
  assert.match(out, /本益比/);
});

test("題數用完：回說明、不呼叫 AI", async () => {
  const { hmacHex } = await import("../functions/_lib/session.js");
  usage = [{ who: (await hmacHex("s", "line:U1")).slice(0, 24), n: 5 }];
  assert.match((await send(atBot("什麼是本益比？")))[0], /每人每天最多 5 題/);
  assert.equal(groqCalls.length, 0);
});

test("沒開通的群組：什麼都不回", async () => {
  approved = 0;
  assert.deepEqual(await send({ text: "2330" }), []);
  assert.deepEqual(await send(atBot("什麼是本益比？")), []);
});
