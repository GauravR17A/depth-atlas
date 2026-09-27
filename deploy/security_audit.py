"""Record exact-pin PyPI advisories and likely secret signatures, without values.

Run from the repository root. This is a point-in-time check, not a penetration
test or a substitute for advisory monitoring. npm audit is run separately.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SIGNATURES = {
    'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'aws_access_id': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'github_token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b'),
    'openai_project_key': re.compile(rb'\bsk-proj-[A-Za-z0-9_-]{45,}\b'),
    'slack_token': re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
}


def advisory(pin):
    name, version = pin
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    try:
        with urlopen(url, timeout=20) as response:
            data = json.load(response)
        return {'name': name, 'version': version, 'source': url, 'status': 'checked',
                'vulnerabilities': [{'id': v['id'], 'aliases': v.get('aliases', []),
                                     'link': v.get('link'), 'fixed_in': v.get('fixed_in', []),
                                     'withdrawn': v.get('withdrawn')} for v in data.get('vulnerabilities', [])]}
    except (HTTPError, URLError, ValueError, TimeoutError) as exc:
        return {'name': name, 'version': version, 'source': url, 'status': 'unavailable', 'error_type': type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    raw = (ROOT/'requirements.txt').read_bytes()
    pins = re.findall(r'^([\w.-]+)==([\w.+-]+)', raw.decode(), flags=re.M)
    with ThreadPoolExecutor(max_workers=6) as pool:
        advisories = list(pool.map(advisory, pins))
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    paths = {ROOT/path for path in tracked if path}
    paths.update((ROOT/'web/dist').rglob('*'))
    findings, scanned = [], 0
    for path in sorted(paths):
        if not path.is_file() or path.stat().st_size > 20_000_000:
            continue
        data = path.read_bytes()
        scanned += 1
        for label, pattern in SIGNATURES.items():
            for match in pattern.finditer(data):
                findings.append({'file': path.relative_to(ROOT).as_posix(), 'line': data[:match.start()].count(b'\n')+1,
                                 'signature': label})
    exposed_names = [p for p in tracked if p and (p.startswith('.vercel/') or Path(p).name.startswith('.env') and Path(p).name != '.env.example')]
    active = [v for row in advisories for v in row.get('vulnerabilities', []) if not v.get('withdrawn')]
    report = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'method': 'Exact runtime requirements queried through PyPI release JSON. Secret signatures scan tracked files and built frontend without recording matching values.',
        'requirements_sha256': hashlib.sha256(raw).hexdigest(), 'dependencies': advisories,
        'active_advisory_count': len(active), 'unavailable_dependency_count': sum(row['status'] != 'checked' for row in advisories),
        'secret_signature_scanned_files': scanned, 'secret_signature_findings': findings, 'tracked_sensitive_paths': exposed_names,
        'limitations': ['Signature scans cannot establish the absence of all secrets.', 'No credential values, ignored env files or personal credential stores are read.',
                       'PyPI advisories do not comprehensively audit native C libraries, operating systems, cloud infrastructure or unknown vulnerabilities.',
                       'Frontend and build dependency advisories use the separate npm audit report.'],
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['active_advisory_count','unavailable_dependency_count','secret_signature_scanned_files','secret_signature_findings','tracked_sensitive_paths']}))
    return 1 if active or findings or exposed_names or report['unavailable_dependency_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
