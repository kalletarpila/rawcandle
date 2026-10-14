"""Export bounded, read-only price-target publication event evidence."""
import argparse
import json
from pathlib import Path
from rawcandle.research.price_target_event_research import build_price_target_event_research


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecasts-db',type=Path,default=Path('data/forecasts.db'))
    parser.add_argument('--canonical-db',type=Path,default=Path('data/fundamentals_v4.db'))
    parser.add_argument('--ohlc-db',type=Path,default=Path('data/osakedata.db'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--metadata-output',type=Path,required=True)
    args = parser.parse_args(argv)
    result = build_price_target_event_research(args.forecasts_db,args.canonical_db,args.ohlc_db,args.output,args.metadata_output)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
