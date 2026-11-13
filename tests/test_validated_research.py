
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from database.provenance import ResearchProvenanceRepository
from database.repository import PaperTradingRepository
from simulator.historical_integrity import HistoricalProvenance
from simulator.validated_research import ValidatedResearchService


UTC = timezone.utc
START = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def candles():
    return pd.DataFrame([
        {
            "timestamp": START + timedelta(minutes=i),
            "Open": 100.0 + i,
            "High": 102.0 + i,
            "Low": 99.0 + i,
            "Close": 100.5 + i,
        }
        for i in range(20)
    ])


def metadata(mode="regular"):
    return HistoricalProvenance(
        provider="SYNTHETIC_TEST_PROVIDER",
        feed_mode=mode,
        retrieved_at=START + timedelta(minutes=20),
    )


def run_trade(service, data=None, **kwargs):
    return service.run(
        signal="UP",
        candles=candles() if data is None else data,
        entry_time=START,
        expiry_minutes=5,
        provenance=kwargs.pop("provenance", metadata()),
        claimed_entry_price=kwargs.pop(
            "claimed_entry_price", 100.0
        ),
        **kwargs,
    )


def test_validated_trade_and_provenance_persist(tmp_path):
    db = tmp_path / "research.db"
    service = ValidatedResearchService(db)

    trade = run_trade(service)

    assert trade.status == "CLOSED"
    assert trade.result == "WIN"
    assert trade.exit_price == pytest.approx(104.5)

    repo = PaperTradingRepository(db)
    saved = repo.get_all_trades()

    assert len(saved) == 1
    assert saved[0].trade_id == trade.trade_id
    assert saved[0].trade_source == "HISTORICAL_RESEARCH"
    assert repo.get_balance() == pytest.approx(10040)

    provenance_repo = ResearchProvenanceRepository(db)
    record = provenance_repo.get(trade.trade_id)

    assert record is not None
    assert record.provider == "SYNTHETIC_TEST_PROVIDER"
    assert record.feed_mode == "regular"
    assert record.validation_version == "6.5.2"


def test_entry_price_mismatch_does_not_write(tmp_path):
    db = tmp_path / "research.db"
    service = ValidatedResearchService(db)

    with pytest.raises(ValueError, match="entry price"):
        run_trade(service, claimed_entry_price=999.0)

    assert service.repository.get_all_trades() == []
    assert service.provenance_repository.count() == 0


def test_missing_middle_candle_does_not_write(tmp_path):
    db = tmp_path / "research.db"
    service = ValidatedResearchService(db)

    incomplete = candles().drop(index=2)

    with pytest.raises(ValueError, match="Missing"):
        run_trade(service, data=incomplete)

    assert service.repository.get_all_trades() == []
    assert service.provenance_repository.count() == 0


def test_unknown_feed_mode_does_not_write(tmp_path):
    db = tmp_path / "research.db"
    service = ValidatedResearchService(db)

    with pytest.raises(ValueError, match="Unknown feed"):
        run_trade(
            service,
            provenance=metadata("unknown"),
        )

    assert service.repository.get_all_trades() == []
    assert service.provenance_repository.count() == 0


def test_transaction_failure_rolls_back_everything(tmp_path):
    db = tmp_path / "research.db"
    service = ValidatedResearchService(db)

    # Deliberately fail provenance INSERT.
    with service.repository.database.connect() as connection:
        connection.execute("""
            CREATE TRIGGER reject_research_provenance
            BEFORE INSERT ON research_provenance
            BEGIN
                SELECT RAISE(ABORT, 'test rollback');
            END
        """)

    with pytest.raises(Exception, match="test rollback"):
        run_trade(service)

    repo = PaperTradingRepository(db)

    assert repo.get_all_trades() == []
    assert repo.get_balance() == pytest.approx(10000)
    assert service.provenance_repository.count() == 0

