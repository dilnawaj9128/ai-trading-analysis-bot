from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class PaperTradingLedger:
    """SQLite-backed paper trading ledger with expiry settlement and model drift monitoring."""

    def __init__(self, db_path: str = "data/paper_trading.db", initial_balance: float = 10000.0) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_balance = initial_balance
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS unified_paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    expiry_minutes INTEGER NOT NULL,
                    signal TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stake REAL NOT NULL,
                    payout_ratio REAL NOT NULL DEFAULT 0.80,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    exit_price REAL,
                    pnl REAL DEFAULT 0.0,
                    settled_at TEXT
                )
                """
            )

    def record_signal(
        self,
        symbol: str,
        expiry_minutes: int,
        signal: str,
        confidence: float,
        entry_price: float,
        stake: float = 100.0,
        payout_ratio: float = 0.80,
    ) -> Optional[int]:
        if signal not in ("UP", "DOWN"):
            return None  # NO TRADE signals are not entered as positions

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO unified_paper_trades (
                    created_at, symbol, expiry_minutes, signal, confidence, entry_price, stake, payout_ratio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol,
                    expiry_minutes,
                    signal,
                    confidence,
                    entry_price,
                    stake,
                    payout_ratio,
                ),
            )
            return int(cur.lastrowid)

    def settle_trade(self, trade_id: int, exit_price: float) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM unified_paper_trades WHERE id = ?", (trade_id,)).fetchone()
            if not row:
                raise ValueError(f"Trade ID {trade_id} not found.")
            if row["status"] != "OPEN":
                return dict(row)

            entry = float(row["entry_price"])
            sig = row["signal"]
            stake = float(row["stake"])
            payout = float(row["payout_ratio"])

            if exit_price == entry:
                status = "DRAW"
                pnl = 0.0
            elif (sig == "UP" and exit_price > entry) or (sig == "DOWN" and exit_price < entry):
                status = "WIN"
                pnl = round(stake * payout, 2)
            else:
                status = "LOSS"
                pnl = round(-stake, 2)

            settled_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE unified_paper_trades
                SET status = ?, exit_price = ?, pnl = ?, settled_at = ?
                WHERE id = ?
                """,
                (status, exit_price, pnl, settled_at, trade_id),
            )
            updated = conn.execute("SELECT * FROM unified_paper_trades WHERE id = ?", (trade_id,)).fetchone()
            return dict(updated)

    def get_performance_and_drift(self, rolling_window: int = 20, min_win_rate: float = 0.52) -> Dict[str, Any]:
        with self._connect() as conn:
            settled = conn.execute(
                "SELECT * FROM unified_paper_trades WHERE status IN ('WIN', 'LOSS', 'DRAW') ORDER BY id ASC"
            ).fetchall()

        total = len(settled)
        wins = sum(1 for r in settled if r["status"] == "WIN")
        losses = sum(1 for r in settled if r["status"] == "LOSS")
        total_pnl = round(sum(float(r["pnl"]) for r in settled), 2)
        balance = round(self.initial_balance + total_pnl, 2)
        win_rate = round(wins / (wins + losses), 4) if (wins + losses) > 0 else 0.0

        recent = settled[-rolling_window:]
        recent_decided = [r for r in recent if r["status"] in ("WIN", "LOSS")]
        recent_wins = sum(1 for r in recent_decided if r["status"] == "WIN")
        recent_win_rate = round(recent_wins / len(recent_decided), 4) if recent_decided else 0.0
        drift_detected = len(recent_decided) >= 10 and recent_win_rate < min_win_rate

        return {
            "total_settled": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "recent_win_rate": recent_win_rate,
            "balance": balance,
            "total_pnl": total_pnl,
            "drift_detected": drift_detected,
        }

    def get_open_trades(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM unified_paper_trades WHERE status = 'OPEN' ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_trades(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM unified_paper_trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
