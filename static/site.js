// 全站共用的動畫：捲動進場、數字跳動、長條展開、即時新聞跑馬燈與快報頁。
// 使用者在系統設定「減少動態效果」時，全部改成直接顯示。
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.classList.add("js");

  // ---- 捲動進場：.sec、卡片、表格列依序淡入 ----
  const targets = document.querySelectorAll(".sec, .stat, .pick, .news, .co, .date-card, .locked, .persona, .obs, .digest-hero li, .bubble, .inv, .rcard");
  targets.forEach((el, i) => {
    el.classList.add("reveal");
    el.style.setProperty("--d", `${(i % 6) * 60}ms`);
  });
  if (reduce || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("in"));
  } else {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }, { rootMargin: "0px 0px -8% 0px" });
    targets.forEach((el) => {
      // 一開始就在畫面裡的直接進場，不等捲動事件
      if (el.getBoundingClientRect().top < innerHeight) requestAnimationFrame(() => el.classList.add("in"));
      else io.observe(el);
    });
    // 保險：不管什麼原因沒觸發（背景分頁、舊瀏覽器），2.5 秒後全部顯示，內容絕不會一直是透明的
    setTimeout(() => targets.forEach((el) => el.classList.add("in")), 2500);
  }

  // ---- 數字跳動：data-count 的元素從 0 數到目標值（只動第一個文字節點，單位與符號保留）----
  const firstText = (node) => {
    while (node && node.nodeType === 1) node = node.firstChild;
    return node && node.nodeType === 3 ? node : null;
  };
  const countUp = (el) => {
    const node = firstText(el);
    const m = node && node.textContent.match(/^(\s*[+\-]?)([\d,]+(?:\.\d+)?)(.*)$/s);
    if (!m) return;
    const [, sign, digits, rest] = m;
    const final = node.textContent;
    setTimeout(() => { node.textContent = final; }, 2500); // 保險：背景分頁動畫被暫停時，也一定回到正確數字
    const target = Number(digits.replace(/,/g, ""));
    const decimals = (digits.split(".")[1] || "").length;
    const start = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - start) / 900);
      const v = target * (1 - Math.pow(1 - p, 3));
      node.textContent = sign + v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + rest;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  if (!reduce && "IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { countUp(e.target); io.unobserve(e.target); }
    });
    document.querySelectorAll("[data-count]").forEach((el) => io.observe(el));
  }

  // ---- 即時快報：首頁跑馬燈與 /news/ 頁 ----
  const ago = (iso) => {
    const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 1) return "剛剛";
    if (m < 60) return `${m} 分鐘前`;
    const h = Math.round(m / 60);
    return h < 24 ? `${h} 小時前` : new Date(iso).toLocaleDateString("zh-TW", { month: "numeric", day: "numeric" });
  };
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const k of kids) if (k != null && k !== "") n.append(k instanceof Node ? k : document.createTextNode(k));
    return n;
  };
  // 太泛的關鍵字不當作產業標籤
  const GENERIC = new Set(["TOP", "headline", "台股", "美股", "國際股", "科技", "產業", "鉅亨速報", "Factset", "外資", "大盤",
    "加權指數", "台積電ADR", "股市", "新聞", "財經", "市場", "經濟", "投資", "盤勢", "個股", "櫃買", "觀察", "焦點",
    "市場預估", "EPS", "目標價", "盤中速報", "美股盤中", "鉅亨看世界", "美股雷達"]);

  async function loadNews(cat = "all") {
    const res = await fetch(`/api/news?cat=${cat}`);
    if (!res.ok) throw new Error("新聞暫時讀不到");
    return res.json();
  }

  // 首頁跑馬燈
  const ticker = document.querySelector("#live-ticker");
  if (ticker) {
    const fill = async () => {
      try {
        const { items } = await loadNews("all");
        ticker.replaceChildren(...items.slice(0, 8).map((i) =>
          el("li", {}, el("span", { class: "pill" }, i.feed_label), el("a", { href: i.url, target: "_blank", rel: "noopener" }, i.title),
            el("span", { class: "time" }, ago(i.time)))));
      } catch (e) { ticker.replaceChildren(el("li", { class: "empty" }, e.message)); }
    };
    fill();
    setInterval(fill, 180_000);
  }

  // 快報頁
  const app = document.querySelector("#news-app");
  if (app) {
    let cat = "all", kw = null, data = null;
    const list = app.querySelector("#news-list"), chips = app.querySelector("#news-chips"), stamp = document.querySelector("#news-updated");
    const render = () => {
      const items = data.items.filter((i) => !kw || i.keywords.includes(kw));
      list.replaceChildren(...(items.length ? items.map((i, n) => {
        const fresh = Date.now() - new Date(i.time) < 30 * 60000;
        return el("a", { class: "nitem reveal in", href: i.url, target: "_blank", rel: "noopener", style: `--d:${Math.min(n, 10) * 40}ms` },
          i.thumb ? el("img", { src: i.thumb, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : el("div", { class: "noimg" }, i.feed_label),
          el("div", { class: "nbody" },
            el("div", { class: "nmeta" }, el("span", { class: "pill" }, i.feed_label), i.category ? el("span", {}, i.category) : "",
              fresh ? el("span", { class: "new" }, "NEW") : "", el("span", { class: "time" }, ago(i.time))),
            el("h3", {}, i.title), el("p", {}, i.summary),
            el("div", { class: "kws" }, ...i.keywords.filter((k) => !GENERIC.has(k)).slice(0, 4).map((k) => el("span", {}, `#${k}`)))));
      }) : [el("p", { class: "empty" }, "這個分類目前沒有新聞")]));
    };
    const renderChips = () => {
      const count = {};
      for (const i of data.items) for (const k of i.keywords) if (!GENERIC.has(k) && k.length <= 8) count[k] = (count[k] || 0) + 1;
      const top = Object.entries(count).filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).slice(0, 14);
      chips.replaceChildren(
        el("button", { class: kw ? "" : "on", onclick: () => { kw = null; renderChips(); render(); } }, "全部"),
        ...top.map(([k, n]) => el("button", { class: kw === k ? "on" : "", onclick: () => { kw = k; renderChips(); render(); } },
          k, el("small", {}, String(n)))));
    };
    const refresh = async () => {
      try {
        data = await loadNews(cat);
        stamp.textContent = `更新於 ${new Date(data.updated).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" })}・每 3 分鐘自動更新`;
        if (kw && !data.items.some((i) => i.keywords.includes(kw))) kw = null;
        renderChips();
        render();
      } catch (e) { list.replaceChildren(el("p", { class: "empty" }, e.message)); }
    };
    for (const b of app.querySelectorAll("#news-tabs button")) b.addEventListener("click", () => {
      cat = b.dataset.cat;
      kw = null;
      app.querySelectorAll("#news-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      refresh();
    });
    refresh();
    setInterval(refresh, 180_000);
  }
})();
