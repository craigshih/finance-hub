// 模擬交易 API。身分來自 Cloudflare Access 登入的 email；所有價格都在伺服器端查，不信任瀏覽器送來的價格。
//
//   GET  /api/sim/me              我的帳戶、持股、近期成交、委託、資產走勢（順便撮合到價的限價單）
//   GET  /api/sim/search?q=       用代號或名稱找股票（例如 2330、台積、元大）
//   GET  /api/sim/quote?code=     查報價（盤中用證交所即時價，收盤後用收盤價）
//   GET  /api/sim/chart?code=     半年日 K、5/20/60 日均線、成交量、四指標體檢
//   POST /api/sim/order           下單 {code, side: buy|sell, shares, type: market|limit, limit_price}
//   POST /api/sim/cancel          取消限價委託 {id}
//   GET  /api/sim/watch           自選股（含報價與四指標體檢）
//   POST /api/sim/watch           加入／移除自選 {code, on: true|false}
//   GET  /api/sim/leaderboard     排行榜（只顯示暱稱）
//   POST /api/sim/nickname        改暱稱 {nickname}
//   POST /api/sim/reset           重新開始（清空持股、委託、走勢，資金回到初始值；自選股保留）

import { accessEmail } from "../../_lib/auth.js";
import { misChannels, parseMis } from "../../_lib/live.js";
import {
  INITIAL_CASH, PublicError, getQuotes, marketOpen, nextClose, orderCost, searchStocks, validateOrder, valuate,
} from "../../_lib/market.js";
import { computeSignals, maSeries, parseYahooChart } from "../../_lib/signals.js";

const UA = "Mozilla/5.0 (compatible; craig-finance-hub/1.0)";
const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

const defaultNickname = (email) => `${email.split("@")[0].slice(0, 2)}***`;
const taipeiDate = (d = new Date()) => new Date(d.getTime() + 8 * 3600_000).toISOString().slice(0, 10);

async function ensurePlayer(db, email) {
  await db
    .prepare("INSERT OR IGNORE INTO players (email, nickname, cash, created_at, resets) VALUES (?, ?, ?, ?, 0)")
    .bind(email, defaultNickname(email), INITIAL_CASH, new Date().toISOString())
    .run();
  return db.prepare("SELECT * FROM players WHERE email = ?").bind(email).first();
}

// ---------- 報價 ----------

async function cached(key, ttl, fetcher) {
  const req = new Request(`https://sim.cache/${key}`);
  const hit = await caches.default.match(req);
  if (hit) return hit.json();
  const data = await fetcher();
  if (data) await caches.default.put(req, new Response(JSON.stringify(data), { headers: { "Cache-Control": `max-age=${ttl}` } }));
  return data;
}

async function liveQuotes(codes) {
  if (!codes.length || !marketOpen()) return {};
  return cached(`live/${[...codes].sort().join(",")}`, 20, async () => {
    try {
      const res = await fetch(`https://mis.twse.com.tw/stock/api/getStockInfo.jsp?json=1&delay=0&ex_ch=${misChannels(codes).join("|")}`,
        { headers: { "User-Agent": UA, Referer: "https://mis.twse.com.tw/stock/index.jsp" } });
      return res.ok ? parseMis(await res.json()) : {};
    } catch {
      return {};
    }
  });
}

// 盤中用即時成交價，其他時間用最近收盤價；source 會顯示在畫面上
async function priceMap(codes, quotes) {
  const live = await liveQuotes(codes);
  const out = {};
  for (const c of codes) {
    const q = quotes[c];
    if (!q) continue;
    const l = live[c];
    out[c] = l ? { ...q, price: l.price, prev: l.prev, chg: l.chg, pct: l.pct, source: "即時", time: l.time }
      : { ...q, source: "收盤", time: null };
  }
  return out;
}

async function quoteOf(code, quotes) {
  if (!/^[0-9A-Z]{4,6}$/.test(code)) throw new PublicError("股票代號格式不正確");
  const q = (await priceMap([code], quotes))[code];
  if (!q) throw new PublicError(`找不到 ${code} 的報價（目前支援上市、上櫃股票與 ETF）`, 404);
  return q;
}

async function chart(code, quotes) {
  const q = quotes[code];
  if (!q) throw new PublicError(`找不到 ${code}`, 404);
  const sym = `${code}.${q.market === "上櫃" ? "TWO" : "TW"}`;
  const rows = await cached(`chart/${sym}`, 600, async () => {
    const res = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${sym}?range=6mo&interval=1d`, { headers: { "User-Agent": UA } });
    if (!res.ok) return null;
    const r = parseYahooChart(await res.json());
    return r.length ? r : null;
  });
  if (!rows) throw new PublicError("走勢資料暫時讀不到", 503);
  const ma5 = maSeries(rows, 5), ma20 = maSeries(rows, 20), ma60 = maSeries(rows, 60);
  const start = Math.max(0, rows.length - 120);
  return {
    code, name: q.name, market: q.market,
    rows: rows.slice(start).map((r, i) => ({ ...r, ma5: ma5[start + i], ma20: ma20[start + i], ma60: ma60[start + i] })),
    signals: computeSignals(rows),
  };
}

// ---------- 交易 ----------

async function execute(db, email, { code, side, shares }, q) {
  const cost = orderCost({ code, side, price: q.price, shares });
  const now = new Date().toISOString();
  const tradeStmt = db
    .prepare("INSERT INTO trades (email, ts, code, name, side, shares, price, amount, fee, tax, price_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(email, now, code, q.name, side, shares, q.price, cost.amount, cost.fee, cost.tax, q.source === "即時" ? `${taipeiDate()} 盤中` : q.date);

  if (side === "buy") {
    // 條件式扣款：同時送出兩張單也不會把現金扣成負數
    const r = await db.prepare("UPDATE players SET cash = cash - ? WHERE email = ? AND cash >= ?").bind(cost.total, email, cost.total).run();
    if (!r.meta.changes) throw new PublicError("現金不足");
    await db.batch([
      db.prepare(`INSERT INTO holdings (email, code, name, shares, cost) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT (email, code) DO UPDATE SET shares = shares + excluded.shares, cost = cost + excluded.cost, name = excluded.name`)
        .bind(email, code, q.name, shares, cost.total),
      tradeStmt,
    ]);
    return { ...cost, realized: null };
  }
  const h = await db.prepare("SELECT shares, cost FROM holdings WHERE email = ? AND code = ?").bind(email, code).first();
  if (!h || h.shares < shares) throw new PublicError(`持股不足（目前 ${h ? h.shares : 0} 股）`);
  const costOut = Math.round((h.cost * shares) / h.shares); // 依比例減少持有成本
  const r = await db.prepare("UPDATE holdings SET shares = shares - ?, cost = cost - ? WHERE email = ? AND code = ? AND shares = ?")
    .bind(shares, costOut, email, code, h.shares).run();
  if (!r.meta.changes) throw new PublicError("持股剛剛有變動，請再試一次", 409);
  const realized = cost.total - costOut;
  await db.batch([
    db.prepare("UPDATE players SET cash = cash + ? WHERE email = ?").bind(cost.total, email),
    db.prepare("DELETE FROM holdings WHERE email = ? AND code = ? AND shares = 0").bind(email, code),
    db.prepare("INSERT INTO sim_realized (email, ts, code, realized) VALUES (?, ?, ?, ?)").bind(email, now, code, realized),
    tradeStmt,
  ]);
  return { ...cost, realized };
}

async function placeOrder(db, email, body) {
  const order = validateOrder(body);
  const type = body?.type === "limit" ? "limit" : "market";
  await ensurePlayer(db, email);
  const q = await quoteOf(order.code, await getQuotes());
  if (type === "limit") {
    const limit = Math.round(Number(body?.limit_price) * 100) / 100;
    if (!(limit > 0) || limit > q.price * 1.5 || limit < q.price * 0.5) throw new PublicError("限價要在現價的 ±50% 以內");
    // 已經到價就直接以現價成交（跟真實市場一樣，以較好的價格成交）
    if ((order.side === "buy" && q.price <= limit) || (order.side === "sell" && q.price >= limit)) {
      const cost = await execute(db, email, order, q);
      return { ok: true, filled: true, ...order, name: q.name, price: q.price, source: q.source, ...cost };
    }
    if (order.side === "sell") {
      const h = await db.prepare("SELECT shares FROM holdings WHERE email = ? AND code = ?").bind(email, order.code).first();
      if (!h || h.shares < order.shares) throw new PublicError(`持股不足（目前 ${h ? h.shares : 0} 股）`);
    }
    const open = await db.prepare("SELECT COUNT(*) AS n FROM sim_orders WHERE email = ? AND status = 'open'").bind(email).first();
    if (open.n >= 20) throw new PublicError("同時最多 20 筆限價委託");
    const expires = nextClose();
    await db.prepare("INSERT INTO sim_orders (email, ts, code, name, side, shares, limit_price, status, expires) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)")
      .bind(email, new Date().toISOString(), order.code, q.name, order.side, order.shares, limit, expires).run();
    return { ok: true, filled: false, ...order, name: q.name, limit_price: limit, expires };
  }
  const cost = await execute(db, email, order, q);
  return { ok: true, filled: true, ...order, name: q.name, price: q.price, source: q.source, price_date: q.date, ...cost };
}

// 限價委託：每次看帳戶時檢查一次，盤中到價就以即時價成交，過了當天收盤就作廢
async function matchOrders(db, email, quotes) {
  const { results: open } = await db.prepare("SELECT * FROM sim_orders WHERE email = ? AND status = 'open'").bind(email).all();
  if (!open.length) return;
  const now = new Date().toISOString();
  const prices = await priceMap([...new Set(open.map((o) => o.code))], quotes);
  for (const o of open) {
    const q = prices[o.code];
    const hit = q && q.source === "即時" && ((o.side === "buy" && q.price <= o.limit_price) || (o.side === "sell" && q.price >= o.limit_price));
    if (hit) {
      let status = "filled", note = `成交價 ${q.price}`;
      try {
        await execute(db, email, o, q);
      } catch (exc) {
        status = "failed"; note = exc instanceof PublicError ? exc.message : "成交失敗";
      }
      await db.prepare("UPDATE sim_orders SET status = ?, note = ? WHERE id = ? AND status = 'open'").bind(status, note, o.id).run();
    } else if (now > o.expires) {
      await db.prepare("UPDATE sim_orders SET status = 'expired', note = '收盤前未成交' WHERE id = ? AND status = 'open'").bind(o.id).run();
    }
  }
}

async function account(db, email) {
  await ensurePlayer(db, email);
  const quotes = await getQuotes();
  await matchOrders(db, email, quotes);
  const player = await db.prepare("SELECT * FROM players WHERE email = ?").bind(email).first();
  const [{ results: holdings }, { results: trades }, { results: orders }, realized] = await Promise.all([
    db.prepare("SELECT code, name, shares, cost FROM holdings WHERE email = ?").bind(email).all(),
    db.prepare("SELECT ts, code, name, side, shares, price, amount, fee, tax, price_date FROM trades WHERE email = ? ORDER BY id DESC LIMIT 50").bind(email).all(),
    db.prepare("SELECT id, ts, code, name, side, shares, limit_price, status, note, expires FROM sim_orders WHERE email = ? ORDER BY id DESC LIMIT 30").bind(email).all(),
    db.prepare("SELECT COALESCE(SUM(realized), 0) AS total FROM sim_realized WHERE email = ?").bind(email).first(),
  ]);
  const prices = { ...quotes, ...(await priceMap(holdings.map((h) => h.code), quotes)) };
  const { rows, value } = valuate(holdings, prices);
  for (const r of rows) {
    r.source = prices[r.code]?.source || "收盤";
    r.day_pct = prices[r.code]?.pct ?? null;
  }
  const total = player.cash + value;
  await db.prepare("INSERT INTO sim_equity (email, date, total) VALUES (?, ?, ?) ON CONFLICT (email, date) DO UPDATE SET total = excluded.total")
    .bind(email, taipeiDate(), Math.round(total)).run();
  const { results: equity } = await db.prepare("SELECT date, total FROM sim_equity WHERE email = ? ORDER BY date DESC LIMIT 120").bind(email).all();
  equity.reverse();
  const prev = equity.length > 1 ? equity[equity.length - 2].total : INITIAL_CASH;
  return {
    nickname: player.nickname, initial: INITIAL_CASH,
    cash: player.cash, holdings_value: value, total, return_pct: (total - INITIAL_CASH) / INITIAL_CASH,
    day_pl: total - prev, realized: realized.total, resets: player.resets,
    holdings: rows, trades, orders, equity,
    market_open: marketOpen(),
    price_date: Object.values(quotes).reduce((d, q) => (q.date && q.date > d ? q.date : d), ""),
  };
}

async function watchlist(db, email, quotes) {
  const { results } = await db.prepare("SELECT code FROM sim_watch WHERE email = ? ORDER BY added").bind(email).all();
  const codes = results.map((r) => r.code).filter((c) => quotes[c]);
  const prices = await priceMap(codes, quotes);
  const signals = await Promise.all(codes.map((c) => chart(c, quotes).then((x) => x.signals).catch(() => null)));
  return { rows: codes.map((c, i) => ({ ...prices[c], signals: signals[i] })) };
}

async function leaderboard(db, email) {
  const [{ results: players }, { results: holdings }, { results: counts }, quotes] = await Promise.all([
    db.prepare("SELECT email, nickname, cash FROM players").all(),
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
      holdings: (byEmail[p.email] || []).length, trades: tradeCount[p.email] || 0,
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
  const url = new URL(request.url);
  const route = [].concat(params.route || []).join("/");
  const method = request.method;
  const code = () => String(url.searchParams.get("code") || "").trim().toUpperCase();
  try {
    if (method === "GET" && route === "me") return json(await account(db, email));
    if (method === "GET" && route === "search") return json({ rows: searchStocks(await getQuotes(), url.searchParams.get("q")) });
    if (method === "GET" && route === "quote") return json(await quoteOf(code(), await getQuotes()));
    if (method === "GET" && route === "chart") return json(await chart(code(), await getQuotes()));
    if (method === "GET" && route === "leaderboard") return json(await leaderboard(db, email));
    if (method === "GET" && route === "watch") return json(await watchlist(db, email, await getQuotes()));
    if (method === "POST" && route === "order") return json(await placeOrder(db, email, await request.json()));
    if (method === "POST" && route === "cancel") {
      const id = Number((await request.json())?.id);
      const r = await db.prepare("UPDATE sim_orders SET status = 'cancelled', note = '自行取消' WHERE id = ? AND email = ? AND status = 'open'").bind(id, email).run();
      if (!r.meta.changes) throw new PublicError("這筆委託已經成交或不存在");
      return json({ ok: true });
    }
    if (method === "POST" && route === "watch") {
      const body = await request.json();
      const c = String(body?.code || "").trim().toUpperCase();
      if (!(await getQuotes())[c]) throw new PublicError("找不到這檔股票");
      if (body?.on === false) {
        await db.prepare("DELETE FROM sim_watch WHERE email = ? AND code = ?").bind(email, c).run();
      } else {
        const n = await db.prepare("SELECT COUNT(*) AS n FROM sim_watch WHERE email = ?").bind(email).first();
        if (n.n >= 30) throw new PublicError("自選股最多 30 檔");
        await db.prepare("INSERT OR IGNORE INTO sim_watch (email, code, added) VALUES (?, ?, ?)").bind(email, c, new Date().toISOString()).run();
      }
      return json({ ok: true });
    }
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
        db.prepare("DELETE FROM sim_orders WHERE email = ?").bind(email),
        db.prepare("DELETE FROM sim_equity WHERE email = ?").bind(email),
        db.prepare("DELETE FROM sim_realized WHERE email = ?").bind(email),
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
