// 模擬交易的報價與交易成本。
// 報價：證交所（上市）與櫃買中心（上櫃）OpenAPI 的每日收盤價，跟 investment-team/market.py 同一個來源。

export const INITIAL_CASH = 1_000_000;
export const FEE_RATE = 0.001425;
export const MAX_SHARES = 10_000_000;

const TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL";
const TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes";
const CACHE_MS = 30 * 60_000;

export class PublicError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

// 證交稅：股票 0.3%，ETF 0.1%，債券 ETF（代號 00 開頭、B 結尾）免徵
export function taxRate(code) {
  if (/^00\w*B$/.test(code)) return 0;
  if (code.startsWith("00")) return 0.001;
  return 0.003;
}

// 手續費無條件捨去；整股最低 20 元、零股最低 1 元（多數券商的零股優惠）
export function orderCost({ code, side, price, shares }) {
  const amount = Math.round(price * shares);
  const fee = Math.max(shares % 1000 === 0 ? 20 : 1, Math.floor(amount * FEE_RATE));
  const tax = side === "sell" ? Math.floor(amount * taxRate(code)) : 0;
  const total = side === "buy" ? amount + fee : amount - fee - tax;
  return { amount, fee, tax, total };
}

export function validateOrder(body) {
  const code = String(body?.code || "").trim().toUpperCase();
  const side = body?.side;
  const shares = Number(body?.shares);
  if (!/^[0-9A-Z]{4,6}$/.test(code)) throw new PublicError("股票代號格式不正確");
  if (side !== "buy" && side !== "sell") throw new PublicError("買賣別不正確");
  if (!Number.isInteger(shares) || shares < 1 || shares > MAX_SHARES) throw new PublicError("股數要是 1 以上的整數");
  return { code, side, shares };
}

function rocDate(s) {
  if (!/^\d{7}$/.test(s || "")) return null;
  return `${Number(s.slice(0, 3)) + 1911}-${s.slice(3, 5)}-${s.slice(5, 7)}`;
}

export function parseQuotes(twseRows, tpexRows) {
  const out = {};
  for (const r of twseRows || []) {
    const close = Number(String(r.ClosingPrice).replace(/,/g, ""));
    if (close > 0) out[r.Code] = { code: r.Code, name: r.Name, price: close, date: rocDate(r.Date), market: "上市" };
  }
  for (const r of tpexRows || []) {
    const close = Number(String(r.Close).replace(/,/g, ""));
    if (close > 0) out[r.SecuritiesCompanyCode] = {
      code: r.SecuritiesCompanyCode, name: r.CompanyName, price: close, date: rocDate(r.Date), market: "上櫃",
    };
  }
  return out;
}

let memo = { quotes: null, at: 0 };

async function fetchJson(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} ${res.status}`);
  return res.json();
}

export async function getQuotes() {
  if (memo.quotes && Date.now() - memo.at < CACHE_MS) return memo.quotes;
  const [twse, tpex] = await Promise.allSettled([fetchJson(TWSE), fetchJson(TPEX)]);
  const quotes = parseQuotes(
    twse.status === "fulfilled" ? twse.value : [],
    tpex.status === "fulfilled" ? tpex.value : [],
  );
  if (!Object.keys(quotes).length) {
    if (memo.quotes) return memo.quotes; // 來源暫時掛掉時沿用舊報價
    throw new PublicError("報價暫時無法取得，請稍後再試", 503);
  }
  memo = { quotes, at: Date.now() };
  return quotes;
}

// 持股估值：用最新收盤價，沒有報價的（例如已下市）以成本計
export function valuate(holdings, quotes) {
  let value = 0;
  const rows = holdings.map((h) => {
    const q = quotes[h.code];
    const price = q ? q.price : null;
    const mv = price != null ? Math.round(price * h.shares) : h.cost;
    value += mv;
    return {
      code: h.code, name: h.name || q?.name || h.code, shares: h.shares, cost: h.cost,
      avg_cost: h.shares ? h.cost / h.shares : 0, price, value: mv, pl: mv - h.cost,
      pl_pct: h.cost ? (mv - h.cost) / h.cost : 0,
    };
  });
  rows.sort((a, b) => b.value - a.value);
  return { rows, value };
}
