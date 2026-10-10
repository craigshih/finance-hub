-- 模擬交易資料庫（Cloudflare D1）。每次部署都會執行，所以全部用 IF NOT EXISTS。
CREATE TABLE IF NOT EXISTS players (
  email      TEXT PRIMARY KEY,           -- 來自 Cloudflare Access 登入，不會顯示給其他人
  nickname   TEXT NOT NULL,
  cash       INTEGER NOT NULL,           -- 新台幣整數
  created_at TEXT NOT NULL,
  resets     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS holdings (
  email  TEXT NOT NULL,
  code   TEXT NOT NULL,
  name   TEXT,
  shares INTEGER NOT NULL,
  cost   INTEGER NOT NULL,               -- 持有成本（含買進手續費）
  PRIMARY KEY (email, code)
);
CREATE TABLE IF NOT EXISTS trades (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  email      TEXT NOT NULL,
  ts         TEXT NOT NULL,
  code       TEXT NOT NULL,
  name       TEXT,
  side       TEXT NOT NULL,              -- buy / sell
  shares     INTEGER NOT NULL,
  price      REAL NOT NULL,
  amount     INTEGER NOT NULL,
  fee        INTEGER NOT NULL,
  tax        INTEGER NOT NULL,
  price_date TEXT
);
CREATE INDEX IF NOT EXISTS trades_by_email ON trades (email, id);
-- AI 投資顧問：問過但還不在每日計算範圍的股票，build 時加入範圍（隔天就有風控與回測）
CREATE TABLE IF NOT EXISTS advisor_watch (
  code     TEXT PRIMARY KEY,
  added_at TEXT NOT NULL
);
-- 模擬交易 v2：限價委託、自選股、每日資產快照、已實現損益
CREATE TABLE IF NOT EXISTS sim_orders (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  email       TEXT NOT NULL,
  ts          TEXT NOT NULL,
  code        TEXT NOT NULL,
  name        TEXT,
  side        TEXT NOT NULL,             -- buy / sell
  shares      INTEGER NOT NULL,
  limit_price REAL NOT NULL,
  status      TEXT NOT NULL,             -- open / filled / cancelled / expired / failed
  note        TEXT,
  expires     TEXT NOT NULL              -- 當天收盤（台北 13:30）
);
CREATE INDEX IF NOT EXISTS sim_orders_by_email ON sim_orders (email, status);
CREATE TABLE IF NOT EXISTS sim_watch (
  email TEXT NOT NULL,
  code  TEXT NOT NULL,
  added TEXT NOT NULL,
  PRIMARY KEY (email, code)
);
CREATE TABLE IF NOT EXISTS sim_equity (
  email TEXT NOT NULL,
  date  TEXT NOT NULL,                   -- 台北日期
  total INTEGER NOT NULL,
  PRIMARY KEY (email, date)
);
CREATE TABLE IF NOT EXISTS sim_realized (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  email    TEXT NOT NULL,
  ts       TEXT NOT NULL,
  code     TEXT NOT NULL,
  realized INTEGER NOT NULL              -- 賣出實收 − 對應的持有成本
);
-- AI 投資機器人（訪客版）每人每天的題數；who 是 email 的 HMAC，不存 email 本身
CREATE TABLE IF NOT EXISTS robot_usage (
  day TEXT NOT NULL,
  who TEXT NOT NULL,
  n   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, who)
);
