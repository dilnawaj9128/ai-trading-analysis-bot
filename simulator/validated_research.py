
"""
Stage 6.5.2 - Strict, atomic historical research workflow.

This is a paper simulation, not broker execution.
"""

from database.provenance import (
    ResearchProvenanceRecord,
    ResearchProvenanceRepository,
)
from database.repository import PaperTradingRepository
from simulator.historical_integrity import (
    validate_historical_trade,
)
from simulator.paper_trading import PaperTradingSimulator


class ValidatedResearchService:
    def __init__(self, db_path="data/paper_trading.db"):
        self.repository = PaperTradingRepository(db_path)
        self.provenance_repository = (
            ResearchProvenanceRepository(db_path)
        )

    def run(
        self,
        *,
        signal,
        candles,
        entry_time,
        expiry_minutes,
        provenance,
        stake=50.0,
        payout_rate=0.80,
        claimed_entry_price=None,
    ):
        """
        Validate, simulate and atomically persist one research trade.

        The caller supplies an already-determined historical signal.
        This method does not generate trading signals.
        """

        if signal not in ("UP", "DOWN"):
            raise ValueError("Research signal must be UP or DOWN.")

        validated = validate_historical_trade(
            candles=candles,
            entry_time=entry_time,
            expiry_minutes=expiry_minutes,
            provenance=provenance,
            claimed_entry_price=claimed_entry_price,
        )

        # Read the current shared paper account.
        # The repository may initialize an empty account.
        self.repository.get_or_create_account(10000.0)
        current_balance = self.repository.get_balance()

        # Run the existing settlement logic in memory.
        # No database writes occur until the final transaction.
        simulator = PaperTradingSimulator(
            initial_balance=current_balance
        )

        trade = simulator.open_trade(
            signal=signal,
            entry_price=validated.entry_price,
            stake=stake,
            expiry_minutes=expiry_minutes,
            entry_time=validated.entry_time,
            payout_rate=payout_rate,
            trade_source="HISTORICAL_RESEARCH",
            data_quality_status="VALID",
        )

        result = simulator.settle_historical_trade(
            trade_id=trade.trade_id,
            candles=candles,
            retrieved_at=provenance.retrieved_at,
        )

        # Verify the settlement matches the strict validator.
        if (
            result.exit_price != validated.expiry_price
            or result.exit_time != validated.expiry_time
            or result.expiry_price_time
            != validated.expiry_candle_time
        ):
            raise ValueError(
                "Settlement differs from validated candle data."
            )

        record = ResearchProvenanceRecord(
            trade_id=result.trade_id,
            provider=provenance.provider,
            feed_mode=provenance.feed_mode,
            symbol=provenance.symbol,
            timeframe=provenance.timeframe,
            retrieved_at=provenance.retrieved_at,
        )

        # One transaction: trade + provenance + account balance.
        # An error rolls back all three writes.
        with self.repository.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_trades (
                    trade_id, direction, entry_price, stake,
                    payout_rate, expiry_minutes, entry_time,
                    status, exit_price, exit_time, result,
                    profit_loss, trade_source, price_source,
                    expiry_price_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.trade_id,
                    result.direction,
                    result.entry_price,
                    result.stake,
                    result.payout_rate,
                    result.expiry_minutes,
                    result.entry_time.isoformat(),
                    result.status,
                    result.exit_price,
                    result.exit_time.isoformat(),
                    result.result,
                    result.profit_loss,
                    result.trade_source,
                    result.price_source,
                    result.expiry_price_time.isoformat(),
                ),
            )

            connection.execute(
                """
                INSERT INTO research_provenance (
                    trade_id, provider, feed_mode, symbol,
                    timeframe, retrieved_at, validation_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.trade_id,
                    record.provider,
                    record.feed_mode,
                    record.symbol,
                    record.timeframe,
                    record.retrieved_at.isoformat(),
                    record.validation_version,
                ),
            )

            cursor = connection.execute(
                """
                UPDATE paper_account
                SET balance = ?
                WHERE id = 1 AND balance = ?
                """,
                (simulator.balance, current_balance),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Paper account changed during research run."
                )

        return result

