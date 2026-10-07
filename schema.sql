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
