// LINE 機器人：webhook 簽章驗證、「今日一檔」關鍵字
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";

import { ASK_WORDS, validSignature } from "../functions/_lib/line.js";

test("簽章正確才放行，竄改內容或沒有簽章都拒絕", async () => {
  const secret = "test-channel-secret";
  const body = JSON.stringify({ events: [{ type: "join", source: { type: "group", groupId: "Cabc" } }] });
  const sig = createHmac("sha256", secret).update(body).digest("base64");
  assert.ok(await validSignature(secret, body, sig));
  assert.ok(!(await validSignature(secret, body.replace("join", "leave"), sig)));
  assert.ok(!(await validSignature(secret, body, "")));
  assert.ok(!(await validSignature("", body, sig)));
});

test("群組裡打「今日一檔」才回覆，聊天內容提到一檔不會誤觸發", () => {
  for (const t of ["今日一檔", "每日一檔", "今日一檔？", "一檔!"]) assert.ok(ASK_WORDS.test(t), t);
  for (const t of ["今天那一檔不錯", "今日一檔怎麼還沒來", "hello"]) assert.ok(!ASK_WORDS.test(t), t);
});
