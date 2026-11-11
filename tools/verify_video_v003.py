"""Run full technical delivery QA under the explicit slower binary policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

if __package__:
    from . import verify_video as base
    from .verify_binary_production_v003 import validate_policy
else:
    import verify_video as base
    from verify_binary_production_v003 import validate_policy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        timeline=json.loads(args.timeline.read_text(encoding='utf-8-sig'))
        bounds=validate_policy(timeline)
        report=base.verify_video(args.video,args.output_dir,args.timeline,duration_bounds=bounds)
        print(json.dumps({'status':report['status'],'report':str(args.output_dir/base.REPORT_NAME),
                          'failed_checks':[name for name,passed in report['checks'].items() if not passed],
                          'measurements':report['measurements']}))
        return 0 if report['status']=='pass' else 1
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(f'Technical revision QA failed: {error}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
