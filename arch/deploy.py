#!/usr/bin/env python3
"""Deploy one fully embedded routing version and verify the published phase."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
from state import STATUS


def deploy(phase, candidate, active):
    root = Path(__file__).resolve().parent
    config = json.loads((root/'generated/index.json').read_text())
    if config['phase'] != phase or config['candidate'] != candidate or config['active'] != active:
        raise ValueError('Generated Worker does not match the deployment phase')
    with tempfile.TemporaryDirectory(prefix='wrangler-output-') as directory:
        output = Path(directory)/'output.jsonl'
        environment = dict(os.environ, WRANGLER_OUTPUT_FILE_PATH=str(output), WRANGLER_SEND_METRICS='false')
        subprocess.run(['pnpm', 'exec', 'wrangler', 'versions', 'upload', '--no-bundle',
                        '--message', f'{phase} snapshot {candidate}'], cwd=root, env=environment, check=True)
        records = [json.loads(line) for line in output.read_text().splitlines() if line.strip()]
        versions = [r['version_id'] for r in records if r.get('type') == 'version-upload']
        if len(versions) != 1:
            raise ValueError('Wrangler did not report exactly one uploaded Worker version')
        subprocess.run(['pnpm', 'exec', 'wrangler', 'versions', 'deploy', versions[0]+'@100%',
                        '--yes', '--message', f'{phase} snapshot {candidate}'],
                       cwd=root, env=environment, check=True)
    # Confirm the completed deployment serves compatible routes before the next
    # phase. This is an operational gate, not a global consistency guarantee.
    for attempt in range(30):
        try:
            request = urllib.request.Request(STATUS+'?candidate='+candidate, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=15) as response:
                status = json.load(response)
            if all(status.get(k) == config[k] for k in ['active', 'candidate', 'phase']):
                print('Verified deployed phase:', phase, active)
                return
        except (OSError, ValueError):
            pass
        time.sleep(5)
    raise RuntimeError('Published Worker did not reach the expected deployment phase')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'active'])
    parser.add_argument('candidate')
    parser.add_argument('active')
    args = parser.parse_args()
    deploy(args.phase, args.candidate, args.active)
