"""Anonymous, bounded deployment-byte checks for the P15 public release.

This complements the scientific HTTP verifier and browser suites. It does not
claim scientific acceptance. No authentication, retries, raw response bodies,
credentials or runtime logs are written to the evidence report.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'web' / 'dist'
VERSION = '0.15.2'
CASE_IDS = {
    'bay-bengal-2024-01', 'arabian-sea-2024-01',
    'pacific-godas-2013-son', 'pacific-godas-2015-son', 'pacific-godas-2022-son',
}
STATIC_PAGES = {
    '/': 'index.html', '/privacy': 'privacy.html', '/terms': 'terms.html',
    '/data-access': 'data-access.html', '/favicon.svg': 'favicon.svg',
    '/third-party-notices.txt': 'third-party-notices.txt',
}
PRIVATE_PATHS = (
    '/.env', '/.vercel/project.json', '/web/src/App.tsx',
    '/docs/PROJECT_STATE.md', '/docs/evidence/p15-local-server.log',
)
MAX_BYTES = 8_000_000
MAX_REQUESTS = 40
REQUEST_SECONDS = 40
RUN_SECONDS = 300


class SameOriginRedirects(HTTPRedirectHandler):
    max_redirections = 3

    def __init__(self, base):
        self.origin = urlsplit(base)[:2]

    def redirect_request(self, request, fp, code, message, headers, newurl):
        resolved = urljoin(request.full_url, newurl)
        if urlsplit(resolved)[:2] != self.origin:
            raise ValueError('A release request redirected outside the selected origin.')
        return super().redirect_request(request, fp, code, message, headers, resolved)


class AssetLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        value = attributes.get('src' if tag == 'script' else 'href' if tag == 'link' else '')
        if value:
            path = urlsplit(value).path
            if path.startswith('/assets/') and path.endswith(('.js', '.css')):
                self.paths.add(path)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Public HTTPS deployment origin, without a query.')
    parser.add_argument('--report', required=True, type=Path, help='New JSON evidence path; existing files are not overwritten.')
    parser.add_argument('--deployment-id', required=True)
    args = parser.parse_args()
    base = args.url.rstrip('/')
    parts = urlsplit(base)
    if parts.scheme != 'https' or not parts.netloc or parts.username or parts.password or parts.path or parts.query or parts.fragment:
        parser.error('--url must be an anonymous HTTPS origin with no path, query or credentials.')
    if args.report.exists():
        parser.error('The report path already exists. Use a new path to preserve previous evidence.')
    if json.loads((ROOT / 'api' / 'release.json').read_text(encoding='utf-8'))['version'] != VERSION:
        parser.error(f'The local release manifest is not {VERSION}.')

    # Checking every built asset also covers dynamic scene and region-mesh
    # imports that are not directly linked in the HTML entry point.
    asset_paths = sorted(
        '/' + path.relative_to(DIST).as_posix()
        for path in (DIST / 'assets').rglob('*')
        if path.is_file() and path.suffix in {'.js', '.css'}
    )
    if not asset_paths or len(STATIC_PAGES) + len(asset_paths) + len(PRIVATE_PATHS) + 2 > MAX_REQUESTS:
        parser.error('Built assets are missing or this release exceeds the bounded request budget.')
    local = {path: (DIST / relative).read_bytes() for path, relative in STATIC_PAGES.items()}
    local.update({path: (DIST / path.lstrip('/')).read_bytes() for path in asset_paths})
    linked = AssetLinks()
    for path in ('/', '/privacy', '/terms', '/data-access'):
        linked.feed(local[path].decode('utf-8'))
    if not linked.paths or not linked.paths.issubset(asset_paths):
        parser.error('A referenced HTML asset is missing from the local build.')

    started = perf_counter()
    report = dict(
        checked_at=datetime.now(timezone.utc).isoformat(), base_url=base,
        deployment_id=args.deployment_id, release=VERSION, anonymous=True,
        retries=0, request_count=0, request_timeout_seconds=REQUEST_SECONDS,
        total_budget_seconds=RUN_SECONDS, response_limit_bytes=MAX_BYTES,
        local_dist='web/dist', directly_referenced_assets=sorted(linked.paths),
        all_built_js_css_assets=asset_paths, checks=[], complete=False, passed=False,
    )
    opener = build_opener(SameOriginRedirects(base))

    def checkpoint():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    def request(path):
        remaining = RUN_SECONDS - (perf_counter() - started)
        if remaining <= 0 or report['request_count'] >= MAX_REQUESTS:
            raise TimeoutError('The bounded release-verification budget was exhausted.')
        report['request_count'] += 1
        request = Request(base + path, headers={
            'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache',
            'User-Agent': 'Ocean-Navigator-P15-Release-Check/1.0',
        })
        try:
            response = opener.open(request, timeout=min(REQUEST_SECONDS, remaining))
        except HTTPError as error:
            response = error
        with response:
            payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError('Response exceeded the bounded byte limit.')
            return response.status, payload, response.headers

    def check(path, kind, validator):
        item = dict(path=path, kind=kind, passed=False)
        try:
            status, body, headers = request(path)
            item.update(status=status, bytes=len(body), sha256=digest(body), content_type=headers.get('Content-Type'))
            item.update(validator(status, body, headers))
            item['passed'] = True
        except Exception as error:
            # Exception type and a controlled message are enough to diagnose a
            # failed check. Never serialize a response body or headers wholesale.
            item.update(error_type=type(error).__name__, error=str(error)[:500])
        report['checks'].append(item)
        checkpoint()

    def health(status, body, headers):
        assert status == 200, 'Health did not return HTTP 200.'
        value = json.loads(body)
        expected = dict(status='ok', service='Depth Atlas', version=VERSION,
                        data_status='historical_case_ready', case_count=5)
        assert all(value.get(key) == field for key, field in expected.items()), 'Health release, state or case count differs.'
        assert headers.get('X-Ocean-App-Version') == VERSION, 'Health version header differs.'
        return dict(health=expected)

    def catalog(status, body, _headers):
        assert status == 200, 'Catalogue did not return HTTP 200.'
        value = json.loads(body)
        ids = [case['id'] for case in value['cases']]
        assert len(ids) == 5 and set(ids) == CASE_IDS, 'The public catalogue does not contain exactly the five expected cases.'
        return dict(case_ids=sorted(ids), case_count=len(ids))

    def same_bytes(path):
        def validate(status, body, _headers):
            assert status == 200, 'Static resource did not return HTTP 200.'
            assert body == local[path], 'Public bytes differ from the local production build.'
            return dict(matches_local=True, local_sha256=digest(local[path]))
        return validate

    def not_exposed(status, body, _headers):
        if status == 404:
            return dict(exposure='not_found')
        if status == 200 and body == local['/']:
            return dict(exposure='exact_index_fallback', matches_local_index=True)
        raise AssertionError('Expected HTTP 404 or an exact index fallback at this private path.')

    checkpoint()
    check('/api/health', 'health', health)
    check('/api/catalog', 'catalogue', catalog)
    for path in [*STATIC_PAGES, *asset_paths]:
        check(path, 'public_build_bytes', same_bytes(path))
    for path in PRIVATE_PATHS:
        check(path, 'private_path_not_published', not_exposed)
    report.update(complete=True, passed=all(item['passed'] for item in report['checks']),
                  elapsed_seconds=round(perf_counter() - started, 3))
    checkpoint()
    print(json.dumps(dict(report=str(args.report), passed=report['passed'],
                          checks=len(report['checks']), requests=report['request_count'], retries=0)))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
