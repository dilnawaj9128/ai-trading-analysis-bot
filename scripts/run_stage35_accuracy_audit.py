"""Stage 35 statistical audit, based only on supplied backtest win/loss counts.

The CLI does not place orders, fetch API data, or assert provenance.
"""
import argparse
from research.stage35_accuracy_audit import audit_accuracy


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wins", type=int, default=7, help="Held-out resolved wins")
    p.add_argument("--losses", type=int, default=9, help="Held-out resolved losses")
    p.add_argument("--pushes", type=int, default=0)
    p.add_argument("--payout", type=float, default=0.80)
    p.add_argument("--min-resolved", type=int, default=100)
    p.add_argument("--independent", action="store_true", help="Only if independently documented")
    p.add_argument("--provider-verified", action="store_true", help="Only if independently documented")
    p.add_argument("--broker-parity-verified", action="store_true", help="Only if independently documented")
    a = p.parse_args()
    result = audit_accuracy(wins=a.wins, losses=a.losses, pushes=a.pushes,
                            payout=a.payout, min_resolved=a.min_resolved,
                            independent=a.independent,
                            provenance_verified=a.provider_verified,
                            broker_parity_verified=a.broker_parity_verified)
    print("STAGE 35 ACCURACY AUDIT (RESEARCH ONLY)")
    for key, value in result.items():
        print(f"{key}: {value}")
    print("Zero real trade calls, zero provider API calls, no accuracy guarantee.")


if __name__ == "__main__":
    main()
