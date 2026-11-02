-- init_macro_news.sql
CREATE TABLE IF NOT EXISTS macro_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    source TEXT,
    title TEXT,
    summary TEXT,
    category TEXT -- FED / BOJ / ECB / INFLATION / LIQUIDITY
);
