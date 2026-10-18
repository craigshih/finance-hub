// LINE Messaging API 的小工具：驗證 webhook 簽章、回覆訊息。
// 金鑰：LINE_CHANNEL_SECRET（驗簽章）、LINE_CHANNEL_ACCESS_TOKEN（呼叫 API），都存在 Cloudflare 的 secrets。

const enc = new TextEncoder();

// X-Line-Signature＝HMAC-SHA256(channel secret, 原始 body) 的 base64
export async function validSignature(secret, body, signature) {
  if (!secret || !signature) return false;
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(body)));
  const b64 = btoa(String.fromCharCode(...sig));
  if (b64.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < b64.length; i++) diff |= b64.charCodeAt(i) ^ signature.charCodeAt(i);
  return diff === 0;
}

// 回覆（reply）不算推播額度；一次最多 5 則
export async function reply(token, replyToken, texts) {
  const messages = texts.filter(Boolean).slice(0, 5).map((text) => ({ type: "text", text: text.slice(0, 5000) }));
  if (!token || !replyToken || !messages.length) return false;
  const res = await fetch("https://api.line.me/v2/bot/message/reply", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ replyToken, messages }),
  });
  if (!res.ok) console.error("LINE reply", res.status, await res.text());
  return res.ok;
}

export const ASK_WORDS = /^(今日一檔|每日一檔|一檔|今天一檔)[!！?？。.\s]*$/;
