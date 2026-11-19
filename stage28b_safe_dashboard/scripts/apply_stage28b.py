"""Apply Stage 28B: refresh signal display from disk every 30 seconds, offline only."""
from pathlib import Path
import argparse

PAGE = Path('dashboard/pages/9_Real_Data_Research.py')
START = 'st.subheader("Market condition and research signal")'
END = '\nwith st.expander("Latest 20 completed candles"):'
MARKER = '# STAGE 28B LIVE SIGNAL DISPLAY'
REPLACE = '''# STAGE 28B LIVE SIGNAL DISPLAY
# A fragment reruns locally every 30 seconds; it NEVER fetches from Twelve Data.
# It must read the CSV and recompute freshness before showing any current bias.
def render_current_signal_panel():
    st.subheader("Market condition and research signal")
    try:
        current_df, current_gaps = load_saved_candles(CSV_PATH)
        current_analysis = analyze_live_candles(current_df)
        current_now = pd.Timestamp(datetime.now(timezone.utc))
        current_open = current_df["timestamp"].iloc[-1]
        current_age = (current_now - current_open).total_seconds()
        current_stale = (
            current_age > STALE_LIMIT_SECONDS
            or current_now < current_open + INTERVAL
        )
        quality = "INVALID" if current_stale or current_gaps else "VALID"
        current_signal = generate_signal(
            current_analysis["frame"], expiry_minutes=15,
            data_mode="unknown", data_quality_status=quality,
        )
        current_market = assess_market(
            current_analysis, stale=current_stale, gaps=current_gaps,
        )
    except (OSError, ValueError, TypeError, KeyError, pd.errors.ParserError):
        st.metric("Signal engine output (15-minute expiry)", "NO TRADE")
        st.error("Saved candles could not be validated; live research unavailable.")
        return
    st.caption(
        f"Signal panel refreshed from local CSV · candle age "
        f"{max(0, current_age)/60:.1f} min · "
        f"{'STALE' if current_stale else 'Recent'}"
    )
    st.info(
        f"Market condition: **{current_market['condition']}** — "
        f"{current_market['explanation']}"
    )
    st.metric("Signal engine output (15-minute expiry)", current_signal["signal"])
    for reason in current_signal.get("reasons", []):
        st.write("•", reason)
    if current_stale or current_gaps:
        st.warning("STALE or incomplete candles: current directional alignment unavailable.")
    elif current_market.get("condition") == "BULLISH ALIGNMENT":
        st.info("Indicator-only research bias: UP alignment (not a trade signal).")
    elif current_market.get("condition") == "BEARISH ALIGNMENT":
        st.info("Indicator-only research bias: DOWN alignment (not a trade signal).")
    else:
        st.info("Indicator-only research bias: inconclusive.")
    st.caption(
        "Unknown broker/feed provenance keeps the strategy at NO TRADE. "
        "Indicator alignment is not a broker-specific prediction."
    )


if hasattr(st, "fragment"):
    render_current_signal_panel = st.fragment(run_every="30s")(
        render_current_signal_panel
    )
render_current_signal_panel()
'''

def patch_page(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError('Unexpected Stage 27A page structure; no changes made')
    before, rest = source.split(START, 1)
    old_middle, after = rest.split(END, 1)
    if ('signal["signal"]' not in old_middle or
            'market' not in old_middle or 'stale' not in old_middle):
        raise RuntimeError('Unrecognized signal block; no changes made')
    return before + REPLACE + END + after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    original = PAGE.read_text(encoding='utf-8')
    updated = patch_page(original)
    if original == updated:
        print('ALREADY PATCHED; no changes made')
    elif args.apply:
        backup = PAGE.with_suffix('.py.stage28a.backup')
        if backup.exists():
            raise RuntimeError('Backup already exists; refusing to overwrite')
        backup.write_text(original, encoding='utf-8')
        PAGE.write_text(updated, encoding='utf-8')
        print('PATCHED:', PAGE)
        print('BACKUP:', backup)
    else:
        print('PREVIEW OK; rerun with --apply to patch')
    print('No HTTP requests; no API credit, journal or probe-state changes.')

if __name__ == '__main__':
    main()
