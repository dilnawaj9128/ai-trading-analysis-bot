"""Offline Stage56 holdout failure analysis; no API calls or trading."""
import argparse
import json
from pathlib import Path
from scripts.stage56_failure_analysis import build_failure_report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv', required=True, action='append')
    p.add_argument('--out-dir', default='data/research/stage56')
    p.add_argument('--payout',type=float,default=0.8)
    p.add_argument('--min-group',type=int,default=10)
    args=p.parse_args(argv)
    if len(args.csv)!=len(set(args.csv)):
        p.error('Duplicate datasets')
    out=Path(args.out_dir)
    out.mkdir(parents=True,exist_ok=True)
    all_ok=True
    for csv in args.csv:
        try:
            report=build_failure_report(csv,payout=args.payout,min_group=args.min_group)
            safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in Path(csv).stem)[:60]
            target=out/f'{safe}_{report["source_sha256"][:16]}_failures.json'
            target.write_text(json.dumps(report,indent=2,sort_keys=True,default=str)+'\n')
            h=report['holdout']
            print('DATASET:',csv,'CANDLES:',report['candles'])
            print('HOLDOUT:',h['wins'],'wins,',h['losses'],'losses,',h['pushes'],'pushes')
            print('NET_UNITS:',h['idealized_net_units'],'STATUS:',report['status'])
            print('REPORT:',target)
        except (ValueError,KeyError,TypeError,ImportError,OSError,AssertionError) as exc:
            all_ok=False
            print('DATASET BLOCKED:',csv,type(exc).__name__,str(exc))
    print('OFFLINE ONLY: No API requests / no broker orders / NO TRADE')
    return 0 if all_ok else 2

if __name__=='__main__':
    raise SystemExit(main())
