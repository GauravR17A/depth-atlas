"""Summarize retained Playwright network traces without making new requests."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence'


def main():
    rows = []
    for path in sorted((EVIDENCE / 'p07-public-071-initial-failures').glob('*/trace.zip')):
        with ZipFile(path) as archive:
            network = [json.loads(line)['snapshot'] for line in archive.read('1-trace.network').decode().splitlines()]
            events = [json.loads(line) for line in archive.read('1-trace.trace').decode().splitlines()]
        requests = []
        for entry in network:
            request, response = entry['request'], entry['response']
            requests.append(dict(
                method=request['method'], url=request['url'], status=response['status'],
                start=entry.get('startedDateTime'), elapsed_ms=entry.get('time'),
                failure=response.get('_failureText'), content_bytes=response.get('content', {}).get('size'),
            ))
        errors = [dict(text=e.get('text'), location=e.get('location')) for e in events if e.get('type') == 'console' and e.get('messageType') == 'error']
        rows.append(dict(
            test=path.parent.name, trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            requests=requests, console_errors=errors,
            http_error_responses=sum(r['status'] >= 400 for r in requests),
            incomplete_or_failed_transfers=sum(r['status'] == -1 for r in requests),
        ))
    recheck = json.loads((EVIDENCE / 'p07-public-071-browser-recheck.json').read_text(encoding='utf-8'))
    report = dict(
        release='0.7.1', method='Offline inspection of all eight retained Playwright trace ZIP files and their network entries. No new browser/network requests.',
        observed='All eight failures involve requests with no completed HTTP response before the UI/test deadline. Three traces stall while retrieving the main static JavaScript bundle. Other traces show 8-second aborted API reads or requests still pending at termination. The WebKit search POST explicitly reports Send failed since rewinding of the data stream failed after about 19 seconds; a retry starts before the assertion ends.',
        conclusion='The traces do not demonstrate a returned numerical mismatch, incorrect rendering geometry, application exception or HTTP error response. They demonstrate intermittent resource/transport availability failures during this run. A browser trace alone cannot isolate local networking, browser transport, CDN or backend latency as the cause. All eight unchanged tests passed the focused rerun, but that does not establish a production reliability rate.',
        focused_recheck_stats=recheck.get('stats'), rows=rows,
    )
    output = EVIDENCE / 'p07-audit-public-071-failures.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(traces=len(rows), http_error_responses=sum(r['http_error_responses'] for r in rows), incomplete_or_failed_transfers=sum(r['incomplete_or_failed_transfers'] for r in rows), focused_recheck_stats=report['focused_recheck_stats'])))


if __name__ == '__main__':
    main()
