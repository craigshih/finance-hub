import assert from "node:assert/strict";
import { test } from "node:test";

import { makeRobotToken, normalizePhrase, phraseMatches, validRobotToken } from "../functions/_lib/robot.js";
import { makeToken, validToken } from "../functions/_lib/session.js";

const env = { SESSION_SECRET: "s", PORTFOLIO_PASSWORD: "owner-pw" };

test("通關語不分大小寫、忽略標點與多餘空白", () => {
  assert.equal(normalizePhrase("  I need  Investment robot!! "), "i need investment robot");
  assert.ok(phraseMatches(env, "I NEED INVESTMENT ROBOT."));
  assert.ok(!phraseMatches(env, "i need robot"));
  assert.ok(!phraseMatches(env, ""));
  assert.ok(phraseMatches({ ...env, ROBOT_PHRASE: "芝麻開門" }, "芝麻開門"));
});

test("機器人與投資頁的 cookie 互不通用", async () => {
  const rb = await makeRobotToken(env);
  const pf = await makeToken(env);
  assert.ok(await validRobotToken(env, rb));
  assert.ok(!(await validToken(env, rb)), "機器人 cookie 不能開投資頁");
  assert.ok(!(await validRobotToken(env, pf)), "投資頁 cookie 也不是機器人 cookie");
  assert.ok(!(await validRobotToken({ ...env, ROBOT_PHRASE: "new phrase" }, rb)), "換通關語後舊 cookie 失效");
});
