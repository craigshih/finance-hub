// 模擬交易 API。身分來自 Cloudflare Access 登入的 email；所有價格都在伺服器端查，不信任瀏覽器送來的價格。
//
//   GET  /api/sim/me            我的帳戶、持股、近期成交
//   GET  /api/sim/quote?code=   查報價與預估成本
//   POST /api/sim/order         下單 {code, side: buy|sell, shares}
//   GET  /api/sim/leaderboard   排行榜（只顯示暱稱）
//   POST /api/sim/nickname      改暱稱 {nickname}
//   POST /api/sim/reset         重新開始（清空持股、資金回到初始值）

import { accessEmail } from "../../_lib/auth.js";
import { INITIAL_CASH, PublicError, getQuotes, orderCost, validateOrder, valuate } from "../../_lib/market.js";

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

const defaultNickname = (email) => `${email.split("@")[0].slice(0, 2)}***`;

async function ensurePlayer(db, email) {
  await db
    .prepare("INSERT OR IGNORE INTO players (email, nickname, cash, created_at, resets) VALUES (?, ?, ?, ?, 0)")
    .bind(email, defaultNickname(email), INITIAL_CASH, new Date().toISOString())
    .run();
  return db.prepare("SELECT * FROM players WHERE email = ?").bind(email).first();
}

async function account(db, email) {
  const player = await ensurePlayer(db, email);
  const [{ results: holdings }, { results: trades }, quotes] = await Promise.all([
    db.prepare("SELECT code, name, shares, cost FROM holdings WHERE email = ?").bind(email).all(),
    db.prepare("SELECT ts, code, name, side, shares, price, amount, fee, tax, price_date FROM trades WHERE email = ? ORDER BY id DESC LIMIT 30")
      .bind(email).all(),
    getQuotes(),
  ]);
  const { rows, value } = valuate(holdings, quotes);
  const total = player.cash + value;
  return {
    nickname: player.nickname, resets: player.resets, initial: INITIAL_CASH,
    cash: player.cash, holdings_value: value, total, return_pct: (total - INITIAL_CASH) / INITIAL_CASH,
    holdings: rows, trades,
    price_date: Object.values(quotes).reduce((d, q) => (q.date && q.date > d ? q.date : d), ""),
  };
}

async function quote(url) {
  const code = String(url.searchParams.get("code") || "").trim().toUpperCase();
  if (!/^[0-9A-Z]{4,6}$/.test(code)) throw new PublicError("股票代號格式不正確");
  const q = (await getQuotes())[code];
  if (!q) throw new PublicError(`找不到 ${code} 的報價（目前支援上市、上櫃股票與 ETF）`, 404);
  return q;
}

async function placeOrder(db, email, body) {
  const { code, side, shares } = validateOrder(body);
  const q = (await getQuotes())[code];
  if (!q) throw new PublicError(`找不到 ${code} 的報價`, 404);
  const cost = orderCost({ code, side, price: q.price, shares });
  await ensurePlayer(db, email);
  const now = new Date().toISOString();
  const tradeStmt = db
    .prepare("INSERT INTO trades (email, ts, code, name, side, shares, price, amount, fee, tax, price_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(email, now, code, q.name, side, shares, q.price, cost.amount, cost.fee, cost.tax, q.date);

  if (side === "buy") {
    // 條件式扣款：同時送出兩張單也不會把現金扣成負數
    const r = await db.prepare("UPDATE players SET cash = cash - ? WHERE email = ? AND cash >= ?")
      .bind(cost.total, email, cost.total).run();
    if (!r.meta.changes) throw new PublicError("現金不足");
    await db.batch([
      db.prepare(`INSERT INTO holdings (email, code, name, shares, cost) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT (email, code) DO UPDATE SET shares = shares + excluded.shares, cost = cost + excluded.cost, name = excluded.name`)
        .bind(email, code, q.name, shares, cost.total),
      tradeStmt,
    ]);
  } else {
    const h = await db.prepare("SELECT shares, cost FROM holdings WHERE email = ? AND code = ?").bind(email, code).first();
    if (!h || h.shares < shares) throw new PublicError(`持股不足（目前 ${h ? h.shares : 0} 股）`);
    const costOut = Math.round((h.cost * shares) / h.shares); // 依比例減少持有成本
    const r = await db.prepare("UPDATE holdings SET shares = shares - ?, cost = cost - ? WHERE email = ? AND code = ? AND shares = ?")
      .bind(shares, costOut, email, code, h.shares).run();
    if (!r.meta.changes) throw new PublicError("持股剛剛有變動，請再試一次", 409);
    await db.batch([
      db.prepare("UPDATE players SET cash = cash + ? WHERE email = ?").bind(cost.total, email),
      db.prepare("DELETE FROM holdings WHERE email = ? AND code = ? AND shares = 0").bind(email, code),
      tradeStmt,
    ]);
  }
  return { ok: true, code, name: q.name, side, shares, price: q.price, price_date: q.date, ...cost };
}

async function leaderboard(db, email) {
  const [{ results: players }, { results: holdings }, { results: counts }, quotes] = await Promise.all([
    db.prepare("SELECT email, nickname, cash, resets FROM players").all(),
    db.prepare("SELECT email, code, name, shares, cost FROM holdings").all(),
    db.prepare("SELECT email, COUNT(*) AS n FROM trades GROUP BY email").all(),
    getQuotes(),
  ]);
  const byEmail = {};
  for (const h of holdings) (byEmail[h.email] ||= []).push(h);
  const tradeCount = Object.fromEntries(counts.map((c) => [c.email, c.n]));
  const rows = players.map((p) => {
    const { value } = valuate(byEmail[p.email] || [], quotes);
    const total = p.cash + value;
    return {
      nickname: p.nickname, total, return_pct: (total - INITIAL_CASH) / INITIAL_CASH,
      holdings: (byEmail[p.email] || []).length, trades: tradeCount[p.email] || 0, resets: p.resets,
      me: p.email === email,
    };
  });
  rows.sort((a, b) => b.total - a.total);
  return { rows };
}

export async function onRequest({ request, env, params }) {
  const email = await accessEmail(request, env);
  if (!email) return json({ error: "需要先登入" }, 401);
  if (!env.DB) return json({ error: "模擬交易資料庫尚未設定" }, 503);

  const db = env.DB;
  const route = [].concat(params.route || []).join("/");
  const method = request.method;
  try {
    if (method === "GET" && route === "me") return json(await account(db, email));
    if (method === "GET" && route === "quote") return json(await quote(new URL(request.url)));
    if (method === "GET" && route === "leaderboard") return json(await leaderboard(db, email));
    if (method === "POST" && route === "order") return json(await placeOrder(db, email, await request.json()));
    if (method === "POST" && route === "nickname") {
      const nickname = String((await request.json())?.nickname || "").trim().slice(0, 20);
      if (!nickname) throw new PublicError("暱稱不能是空的");
      await ensurePlayer(db, email);
      await db.prepare("UPDATE players SET nickname = ? WHERE email = ?").bind(nickname, email).run();
      return json({ ok: true, nickname });
    }
    if (method === "POST" && route === "reset") {
      await ensurePlayer(db, email);
      await db.batch([
        db.prepare("DELETE FROM holdings WHERE email = ?").bind(email),
        db.prepare("DELETE FROM trades WHERE email = ?").bind(email),
        db.prepare("UPDATE players SET cash = ?, resets = resets + 1 WHERE email = ?").bind(INITIAL_CASH, email),
      ]);
      return json({ ok: true });
    }
    return json({ error: "找不到這個功能" }, 404);
  } catch (exc) {
    if (exc instanceof PublicError) return json({ error: exc.message }, exc.status);
    if (exc instanceof SyntaxError) return json({ error: "資料格式不正確" }, 400);
    console.error(exc);
    return json({ error: "系統錯誤，請稍後再試" }, 500);
  }
}
