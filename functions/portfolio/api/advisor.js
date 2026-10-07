// AI 投資顧問：POST /portfolio/api/advisor  { question, history: [{q, headline}] }
// 在 /portfolio/ 底下，所以先經過投資頁的密碼檢查（functions/portfolio/_middleware.js），只有站長能用。
// 資料：build 時產生的 /portfolio/advisor/stocks.json（每日）、holdings.json（持股權重），加上鉅亨網即時新聞。

import {
  MAX_QUESTION, MAX_STOCKS, buildMessages, collectNumbers, compactStock, findStocks, parsePttIndex, pttFor, sanitizeAnswer,
  unverifiedNumbers,
} from "../../_lib/advisor.js";
import { parseRss } from "../../api/news.js";

const MODEL = "openai/gpt-oss-120b";
const UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)";
const PROMPT_NUMBERS = [15, 300, 60, 20, 95, 1.5, 3];
let memo = { at: 0, data: null, holdings: null };

const fail = (error, status = 400) => Response.json({ error }, { status });

async function asset(env, request, path) {
  // 帶上登入 cookie：靜態檔也在密碼保護範圍內
  const res = await env.ASSETS.fetch(new Request(new URL(path, request.url), { headers: { Cookie: request.headers.get("Cookie") || "" } }));
  return res.ok ? res.json() : null;
}

async function loadData(env, request) {
  if (memo.data && Date.now() - memo.at < 10 * 60_000) return memo;
  const [data, holdings] = await Promise.all([
    asset(env, request, "/portfolio/advisor/stocks.json"),
    asset(env, request, "/portfolio/advisor/holdings.json"),
  ]);
  if (data) memo = { at: Date.now(), data, holdings };
  return { data, holdings };
}

// 鉅亨網即時新聞裡，標題點名這幾檔的（只用標題，不改寫內容）
async function relatedNews(stocks) {
  const feeds = ["tw_stock", "headline"];
  const items = (await Promise.all(feeds.map(async (f) => {
    try {
      const res = await fetch(`https://news.cnyes.com/rss/v1/news/category/${f}`, { headers: { "User-Agent": UA } });
      return res.ok ? parseRss(await res.text(), f) : [];
    } catch {
      return [];
    }
  }))).flat();
  const out = {};
  for (const s of stocks) {
    const n = s.name.replace(/-KY$|\*$/, "");
    const seen = new Set();
    out[s.code] = items.filter((i) => (i.title.includes(n) || i.title.includes(s.code)) && !seen.has(i.url) && seen.add(i.url))
      .slice(0, 4).map((i) => ({ title: i.title, url: i.url, time: i.time }));
  }
  return out;
}

// PTT 股板最新 6 頁標題，15 分鐘共用一次
let pttMemo = { at: 0, titles: null };
async function pttTitles() {
  if (pttMemo.titles && Date.now() - pttMemo.at < 15 * 60_000) return pttMemo.titles;
  const titles = [];
  let url = "https://www.ptt.cc/bbs/Stock/index.html";
  try {
    for (let i = 0; i < 6 && url; i++) {
      const res = await fetch(url, { headers: { "User-Agent": UA } });
      if (!res.ok) break;
      const page = parsePttIndex(await res.text());
      titles.push(...page.titles);
      url = page.prev;
    }
  } catch (exc) {
    console.error("ptt", exc);
  }
  if (titles.length) pttMemo = { at: Date.now(), titles };
  return titles;
}

async function askGroq(env, messages) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.GROQ_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: MODEL, messages, max_completion_tokens: 3500, reasoning_effort: "medium",
        temperature: 0.3, response_format: { type: "json_object" },
      }),
    });
    if (res.status === 429 && attempt === 0) {
      await new Promise((r) => setTimeout(r, 4000));
      continue;
    }
    if (!res.ok) throw new Error(`Groq ${res.status}: ${(await res.text()).slice(0, 200)}`);
    const body = await res.json();
    return JSON.parse(body.choices[0].message.content);
  }
  throw new Error("Groq 忙線中");
}

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return fail("格式不正確");
  }
  const question = String(body?.question || "").trim();
  if (!question) return fail("請輸入問題");
  if (question.length > MAX_QUESTION) return fail(`問題請在 ${MAX_QUESTION} 字以內`);
  const { data, holdings } = await loadData(env, request);
  if (!data) return fail("今天的顧問資料還沒產生，請等下一次網站更新", 503);

  let codes = findStocks(question, data.stocks);
  // 問整體持股（集中度、配置）時，帶入權重最大的幾檔持股的資料
  if (!codes.length && holdings && /持股|部位|配置|投資組合|集中|我的股票/.test(question)) {
    codes = holdings.holdings.map((h) => h.code).filter((c) => data.stocks[c]).slice(0, MAX_STOCKS);
  }
  if (!env.GROQ_API_KEY) {
    return Response.json({ error: "AI 金鑰還沒設定（GROQ_API_KEY），暫時無法回答", found: codes }, { status: 503 });
  }
  const priced = new Set(data.price_codes || []);
  const held = Object.fromEntries((holdings?.holdings || []).map((h) => [h.code, h]));

  // 沒在每日計算範圍的股票，記下來，明天起補上風控與回測
  const missing = codes.filter((c) => !priced.has(c));
  if (missing.length && env.DB) {
    const now = new Date().toISOString();
    await env.DB.batch(missing.map((c) => env.DB.prepare("INSERT OR IGNORE INTO advisor_watch (code, added_at) VALUES (?, ?)").bind(c, now)))
      .catch((exc) => console.error("advisor_watch", exc));
  }

  // 每日資料沒有 PTT（build 主機被擋）時，即時抓
  const full = codes.map((c) => ({ ...data.stocks[c] }));
  if (full.some((s) => !s.ptt)) {
    const titles = await pttTitles();
    if (titles.length) for (const s of full) if (!s.ptt) s.ptt = pttFor(s.code, s.name, titles);
  }
  const stocks = full.map((s) => compactStock(s, held[s.code]));
  const news = await relatedNews(stocks);
  const portfolio = holdings ? {
    as_of: holdings.as_of,
    holdings: holdings.holdings.map((h) => ({ code: h.code, name: h.name, weight_pct: h.weight_pct, pl_pct: h.pl_pct })),
  } : null;
  const context = { generated_at: data.generated_at, stocks };

  let answer;
  try {
    const raw = await askGroq(env, buildMessages({ question, data: context, news, history: body.history, portfolio }));
    answer = sanitizeAnswer(raw, codes);
  } catch (exc) {
    console.error(exc);
    return fail("AI 暫時沒有回應，請稍後再試", 502);
  }

  const known = [...collectNumbers(context), ...collectNumbers(portfolio), ...PROMPT_NUMBERS];
  return Response.json({
    answer,
    unverified: unverifiedNumbers(answer, known),
    stocks: full.map((s) => ({ ...s, held: held[s.code] || null, news: news[s.code] || [] })),
    missing_metrics: missing,
    data_date: data.generated_at,
  });
}
