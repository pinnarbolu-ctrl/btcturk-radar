"""
H AI v1.0
Initial Foundation

Commit 1:
- Clean project entry point
- H AI startup
- Modular architecture placeholder
"""

from pathlib import Path
import sqlite3
import logging

APP_NAME = "H AI"
VERSION = "1.0.0"

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "history.db"

DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            price REAL,
            volume REAL
        )
    """)
    conn.commit()
    conn.close()

def startup():
    logging.info(f"{APP_NAME} v{VERSION} starting...")
    init_database()
    logging.info("Database ready.")
    logging.info("Market engine: waiting...")
    logging.info("AI engine: waiting...")
    logging.info("Telegram engine: waiting...")

if __name__ == "__main__":
    startup()
