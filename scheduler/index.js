// 準時排程器（Cloudflare Worker 的 Cron Trigger，誤差 1 分鐘內）：GitHub Actions 的排程常晚好幾小時，
// 所以由這裡在固定時間「叫 GitHub 立刻跑」（workflow_dispatch 幾秒內就開始），程式跑完再等到整點才推 LINE。
//   台北 08:30 → finance-hub 每日一檔（產生後等到 09:00 推群組、寄信）
//   平日台北 13:50（MON-FRI）→ craig-stock-trade-report 股價快報（收盤價寫進 Notion、AI 快報，等到 14:00 私訊站長）
// 金鑰：GH_DISPATCH_TOKEN（fine-grained，只給這兩個 repo 的 Actions: Read and write）

// 注意：Cloudflare 的 cron 星期是 1＝星期日（跟一般 cron 不同），所以平日要寫 MON-FRI，寫 1-5 會變成週日到週四
const PRICE = { repo: "craigshih/craig-stock-trade-report", workflow: "daily-price-update.yml", inputs: {} };
export const JOBS = {
  "30 0 * * *": { repo: "craigshih/finance-hub", workflow: "daily_pick.yml", inputs: { send: "true" } },
  "50 5 * * MON-FRI": PRICE,
  "50 5 * * 1-5": PRICE, // 舊寫法，後台改完之前先保留
};

export async function dispatch(job, token, fetcher = fetch) {
  const res = await fetcher(`https://api.github.com/repos/${job.repo}/actions/workflows/${job.workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json",
      "User-Agent": "craig-finance-scheduler", "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ ref: "main", inputs: job.inputs }),
  });
  if (!res.ok) throw new Error(`${job.repo} ${job.workflow}：${res.status} ${await res.text()}`);
}

export default {
  async scheduled(event, env) {
    const job = JOBS[event.cron];
    if (!job) return console.error("沒有對應的工作", event.cron);
    // 失敗重試兩次（GitHub API 偶爾 5xx）
    for (let i = 0; i < 3; i++) {
      try {
        await dispatch(job, env.GH_DISPATCH_TOKEN);
        return console.log("已觸發", job.repo, job.workflow);
      } catch (exc) {
        console.error(exc.message);
        await new Promise((r) => setTimeout(r, 5000 * (i + 1)));
      }
    }
  },
  // 瀏覽器打開只回一句話，不觸發任何東西
  fetch: () => new Response("craig-finance scheduler"),
};
