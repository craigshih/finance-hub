// 模擬交易頁的前端。所有計算以伺服器回傳為準，這裡只負責顯示與送單。
(() => {
  const $ = (sel) => document.querySelector(sel);
  const fmt = (n, d = 0) => (n == null ? "—" : Number(n).toLocaleString("zh-TW", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const signed = (n) => (n == null ? "—" : (n > 0 ? "+" : "") + fmt(n));
  const pct = (x) => (x == null ? "—" : (x > 0 ? "+" : "") + (x * 100).toFixed(2) + "%");
  const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const k of kids) n.append(k instanceof Node ? k : document.createTextNode(k ?? ""));
    return n;
  };

  // 企業 logo（Financial Modeling Prep 公開圖）：上市 .TW、上櫃 .TWO；沒有圖就顯示首字
  const logo = (code, name, market) => {
    const base = "https://financialmodelingprep.com/image-stock/";
    const urls = /^[0-9]{4,6}[A-Z]?$/.test(code)
      ? (market === "上櫃" ? [`${base}${code}.TWO.png`] : market === "上市" ? [`${base}${code}.TW.png`] : [`${base}${code}.TW.png`, `${base}${code}.TWO.png`])
      : [`${base}${code}.png`];
    const hue = [...code].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
    const wrap = el("span", { class: "logo sm", style: `--h:${hue}` }, el("b", {}, (name || code)[0]));
    const img = el("img", { src: urls[0], alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
    let i = 0;
    img.addEventListener("error", () => { i += 1; if (urls[i]) img.src = urls[i]; else img.remove(); });
    wrap.append(img);
    return wrap;
  };

  // 台股手續費／證交稅，跟伺服器 functions/_lib/market.js 同一套規則，只用於下單前預估
  const taxRate = (code) => (/^00\w*B$/.test(code) ? 0 : code.startsWith("00") ? 0.001 : 0.003);
  const estimate = (code, side, price, shares) => {
    const amount = Math.round(price * shares);
    const fee = Math.max(shares % 1000 === 0 ? 20 : 1, Math.floor(amount * 0.001425));
    const tax = side === "sell" ? Math.floor(amount * taxRate(code)) : 0;
    return { amount, fee, tax, total: side === "buy" ? amount + fee : amount - fee - tax };
  };

  async function api(path, body) {
    const res = await fetch(`/api/sim/${path}`, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({ error: "伺服器沒有回應" }));
    if (!res.ok) throw new Error(data.error || `錯誤 ${res.status}`);
    return data;
  }

  function toast(msg, bad = false) {
    const t = $("#sim-toast");
    t.textContent = msg;
    t.className = "toast show" + (bad ? " bad" : "");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => (t.className = "toast"), 3500);
  }

  let me = null;
  let side = "buy";
  let quote = null;

  function renderAccount() {
    $("#sim-total").textContent = fmt(me.total);
    $("#sim-total-sub").replaceChildren(
      "總報酬 ", el("span", { class: cls(me.return_pct) }, pct(me.return_pct)),
      `・暱稱 ${me.nickname}・報價日期 ${me.price_date || "—"}`,
    );
    const tiles = [
      ["可用現金", fmt(me.cash), ""],
      ["持股市值", fmt(me.holdings_value), `${me.holdings.length} 檔`],
      ["損益", signed(me.total - me.initial), pct(me.return_pct)],
      ["初始資金", fmt(me.initial), me.resets ? `已重來 ${me.resets} 次` : ""],
    ];
    $("#sim-tiles").replaceChildren(...tiles.map(([label, value, foot], i) =>
      el("div", { class: "stat" },
        el("div", { class: "stat-label" }, label),
        el("div", { class: "stat-value " + (i === 2 ? cls(me.total - me.initial) : "") }, value),
        el("div", { class: "stat-foot" }, el("span", {}, foot)))));

    const hb = $("#sim-holdings");
    if (!me.holdings.length) {
      hb.replaceChildren(el("p", { class: "empty" }, "還沒有持股，從右邊下第一張單吧。"));
    } else {
      const rows = me.holdings.map((h) => el("tr", { class: "clickable", title: "點一下帶入賣出", onclick: () => prefill(h.code, "sell", h.shares) },
        el("td", {}, el("span", { class: "name" }, logo(h.code, h.name), el("span", {}, el("b", {}, h.name), el("small", {}, h.code)))),
        el("td", { class: "num" }, fmt(h.shares)),
        el("td", { class: "num" }, fmt(h.avg_cost, 2)),
        el("td", { class: "num" }, fmt(h.price, 2)),
        el("td", { class: "num" }, fmt(h.value)),
        el("td", { class: "num " + cls(h.pl) }, signed(h.pl)),
        el("td", { class: "num " + cls(h.pl_pct) }, pct(h.pl_pct))));
      hb.replaceChildren(el("div", { class: "table-wrap" }, el("table", { class: "holdings" },
        el("thead", {}, el("tr", {}, ...["標的", "股數", "均價", "現價", "市值", "損益", "報酬率"].map((h, i) => el("th", { class: i ? "num" : "" }, h)))),
        el("tbody", {}, ...rows))));
    }

    const tb = $("#sim-trades");
    tb.replaceChildren(...(me.trades.length ? me.trades.map((t) =>
      el("li", {}, el("span", { class: "pill" }, t.side === "buy" ? "買進" : "賣出"),
        `${t.ts.slice(0, 10)} ${t.code} ${t.name || ""} ${fmt(t.shares)} 股 @ ${fmt(t.price, 2)}　手續費 ${fmt(t.fee)}${t.tax ? `・稅 ${fmt(t.tax)}` : ""}`))
      : [el("li", { class: "empty" }, "還沒有成交紀錄")]));
    $("#sim-nickname").value = me.nickname;
  }

  async function loadBoard() {
    const { rows } = await api("leaderboard");
    $("#sim-board").replaceChildren(...rows.map((r, i) => el("tr", { class: r.me ? "me" : "" },
      el("td", { class: "rank" }, String(i + 1)),
      el("td", {}, el("b", {}, r.nickname), r.me ? el("small", {}, "（我）") : "", r.resets ? el("small", {}, ` 重來 ${r.resets} 次`) : ""),
      el("td", { class: "num" }, fmt(r.total)),
      el("td", { class: "num " + cls(r.return_pct) }, pct(r.return_pct)),
      el("td", { class: "num" }, String(r.holdings)),
      el("td", { class: "num" }, String(r.trades)))));
  }

  async function refresh() {
    me = await api("me");
    renderAccount();
    loadBoard().catch((e) => toast(e.message, true));
  }

  function updateEstimate() {
    const shares = Number($("#sim-shares").value);
    const box = $("#sim-estimate");
    if (!quote || !Number.isInteger(shares) || shares < 1) {
      box.replaceChildren(el("span", { class: "muted" }, quote ? "輸入股數後顯示預估金額" : "先查詢股票代號"));
      return;
    }
    const c = estimate(quote.code, side, quote.price, shares);
    const held = me?.holdings.find((h) => h.code === quote.code)?.shares || 0;
    box.replaceChildren(
      el("div", {}, "成交金額", el("b", {}, fmt(c.amount))),
      el("div", {}, "手續費", el("b", {}, fmt(c.fee))),
      side === "sell" ? el("div", {}, "證交稅", el("b", {}, fmt(c.tax))) : "",
      el("div", { class: "est-total" }, side === "buy" ? "需付" : "實收", el("b", {}, fmt(c.total))),
      el("small", {}, side === "buy" ? `買完剩現金 ${fmt((me?.cash || 0) - c.total)}` : `目前持有 ${fmt(held)} 股`),
    );
  }

  async function lookup() {
    const code = $("#sim-code").value.trim().toUpperCase();
    if (!code) return;
    try {
      quote = await api(`quote?code=${encodeURIComponent(code)}`);
      $("#sim-quote").replaceChildren(logo(quote.code, quote.name, quote.market), el("b", {}, `${quote.code} ${quote.name}`),
        el("span", {}, `${fmt(quote.price, 2)}`), el("small", {}, `${quote.market}・${quote.date} 收盤`));
    } catch (e) {
      quote = null;
      $("#sim-quote").replaceChildren(el("span", { class: "muted" }, e.message));
    }
    updateEstimate();
  }

  function setSide(s) {
    side = s;
    for (const b of document.querySelectorAll("#sim-side button")) b.classList.toggle("on", b.dataset.side === s);
    $("#sim-submit").textContent = s === "buy" ? "送出買單" : "送出賣單";
    $("#sim-submit").className = "btn " + (s === "buy" ? "buy" : "sell");
    updateEstimate();
  }

  async function prefill(code, s, shares) {
    $("#sim-code").value = code;
    $("#sim-shares").value = shares;
    setSide(s);
    await lookup();
    $("#sim-order").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function submit(ev) {
    ev.preventDefault();
    const btn = $("#sim-submit");
    btn.disabled = true;
    try {
      const r = await api("order", { code: $("#sim-code").value.trim(), side, shares: Number($("#sim-shares").value) });
      toast(`${r.side === "buy" ? "買進" : "賣出"} ${r.code} ${r.name} ${fmt(r.shares)} 股 @ ${fmt(r.price, 2)}，${r.side === "buy" ? "付出" : "收到"} ${fmt(r.total)}`);
      await refresh();
      updateEstimate();
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
    }
  }

  function init() {
    if (!$("#sim-app")) return;
    $("#sim-form").addEventListener("submit", submit);
    $("#sim-lookup").addEventListener("click", lookup);
    $("#sim-code").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); lookup(); } });
    $("#sim-code").addEventListener("change", lookup);
    $("#sim-shares").addEventListener("input", updateEstimate);
    for (const b of document.querySelectorAll("#sim-side button")) b.addEventListener("click", () => setSide(b.dataset.side));
    for (const b of document.querySelectorAll("[data-lots]")) b.addEventListener("click", () => {
      $("#sim-shares").value = Number(b.dataset.lots) * 1000;
      updateEstimate();
    });
    $("#sim-nick-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("nickname", { nickname: $("#sim-nickname").value });
        toast("暱稱已更新");
        await refresh();
      } catch (err) { toast(err.message, true); }
    });
    $("#sim-reset").addEventListener("click", async () => {
      if (!confirm("確定要重新開始？持股和成交紀錄會清空，資金回到 1,000,000。排行榜會顯示重來次數。")) return;
      try {
        await api("reset", {});
        toast("已重新開始");
        await refresh();
      } catch (err) { toast(err.message, true); }
    });
    setSide("buy");
    refresh().catch((e) => {
      $("#sim-app").prepend(el("div", { class: "soon" }, `讀不到帳戶：${e.message}`));
    });
  }

  init();
})();
