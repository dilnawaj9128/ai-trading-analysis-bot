import time
import math
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("data/research/nifty50/live")
DB = ROOT / "predictions.db"
REPORT = ROOT / "validation_report.json"

TARGET = 100
PAYOUT = 0.80

def wilson_lower(w, n):
    if n == 0:
        return 0.0
    z = 1.96
    p = w / n
    return (
        p + z*z/(2*n)
        - z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    ) / (1+z*z/n)

def evaluate(conn, h):
    rows = conn.execute("""
        SELECT result,entry,exit_price,direction
        FROM predictions
        WHERE horizon=?
        ORDER BY timestamp
    """, (h,)).fetchall()

    wins = sum(r[0] == "WIN" for r in rows)
    losses = sum(r[0] == "LOSS" for r in rows)
    pushes = sum(r[0] == "PUSH" for r in rows)
    pending = sum(r[0] == "PENDING" for r in rows)

    n = wins + losses
    accuracy = wins/n if n else 0
    lower = wilson_lower(wins,n)
    breakeven = 1/(1+PAYOUT)

    pnl = wins*PAYOUT-losses

    equity = 0
    peak = 0
    drawdown = 0
    points = 0

    for result,entry,exit_price,direction in rows:
        if result not in ("WIN","LOSS","PUSH"):
            continue

        equity += (
            PAYOUT if result == "WIN"
            else -1 if result == "LOSS"
            else 0
        )

        peak = max(peak,equity)
        drawdown = max(drawdown,peak-equity)

        if exit_price is not None:
            points += (
                exit_price-entry if direction == "UP"
                else entry-exit_price
            )

    if n < TARGET:
        status = "COLLECTING"
    elif lower > breakeven and pnl > 0:
        status = "RESEARCH_CANDIDATE"
    else:
        status = "EDGE_NOT_ESTABLISHED"

    return {
        "timeframe": h,
        "target": TARGET,
        "verified_directional_results": n,
        "remaining": max(0,TARGET-n),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pending": pending,
        "accuracy_pct": round(accuracy*100,2) if n else None,
        "wilson_lower_pct": round(lower*100,2) if n else None,
        "breakeven_pct": round(breakeven*100,2),
        "hypothetical_pnl_units": round(pnl,2),
        "gross_directional_index_points": round(points,2),
        "max_drawdown_units": round(drawdown,2),
        "status": status,
        "real_money_approved": False
    }

print("===== AUTOMATIC FORWARD VALIDATION =====")
print("TARGET: 100 directional results per timeframe")
print("MODE: ANALYSIS ONLY")

while True:
    try:
        with sqlite3.connect(DB,timeout=10) as conn:
            results = [
                evaluate(conn,h)
                for h in (5,10,15)
            ]

        complete = all(
            r["remaining"] == 0 for r in results
        )

        report = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "collection_complete": complete,
            "hypothetical_payout": PAYOUT,
            "broker_execution": False,
            "real_money_approved": False,
            "results": results
        }

        tmp = REPORT.with_suffix(".tmp")
        tmp.write_text(json.dumps(report,indent=2))
        tmp.replace(REPORT)

        print("\n===== VALIDATION UPDATE =====")

        for r in results:
            print(
                f'{r["timeframe"]}m | '
                f'{r["verified_directional_results"]}/100 | '
                f'WIN={r["wins"]} | '
                f'LOSS={r["losses"]} | '
                f'ACCURACY={r["accuracy_pct"]}% | '
                f'P/L={r["hypothetical_pnl_units"]} | '
                f'{r["status"]}'
            )

        if complete:
            print("100-RESULT TARGET REACHED")
            print("REPORT:",REPORT)
            break

    except Exception as e:
        print("VALIDATION ERROR:",str(e))

    time.sleep(60)
