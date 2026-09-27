"""Bounded P11 deployment, NDJSON, exact replay and export verification.

Local calculations are deployment-consistency references, not independent
scientific validation. Independent original-source, analytical and complete
OceanParcels-runtime tests live in tests/test_drift_independent.py. HTTP requests
have no automatic retries. A fixed request timeout and whole-run budget bound
network work. NDJSON event arrival times are recorded without claiming that
every proxy flushes every server event immediately.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.case_store import CaseStore
from api.drift_store import DriftStore
from science.drift_contracts import DriftQuery, METHOD
from science.verify_p10_public import equivalent, fingerprint, validate_bundle

CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')


def read_records(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    return value['records'] if isinstance(value, dict) and 'records' in value else list(value.values()) if isinstance(value, dict) else value


def query_for(manifest, **overrides):
    c = manifest.coordinates
    x, y = (c.longitude[0]+c.longitude[-1])/2, (c.latitude[0]+c.latitude[-1])/2
    q = dict(release=dict(kind='box', bounds=[x-.15, y-.15, x+.15, y+.15]),
             depth_index=0, start_time_index=0, duration_hours=12, particle_count=8,
             dt_seconds=600, seed=26067, target_bounds=[x-.25, y-.25, x+.25, y+.25])
    q.update(overrides)
    return q


def trajectory_csv(raw, module):
    out = module['output']
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
    expected = [(particle, point) for particle in out['particles'] for point in particle['points']]
    assert len(rows) == len(expected)
    for row, (particle, point) in zip(rows, expected):
        assert row['module'] == module['module']
        assert row['method_version'] == out['method_version'] and row['manifest_sha256'] == out['manifest_sha256']
        assert row['simulated'] == 'True' and row['case_id'] == out['case_id']
        assert float(row['depth_m']) == out['depth_m'] and int(row['seed']) == out['query']['seed']
        assert row['start_time_utc'] == out['start_time']
        stamp = datetime.fromisoformat(out['start_time'].replace('Z', '+00:00')) + timedelta(seconds=point['elapsed_seconds'])
        assert datetime.fromisoformat(row['sample_time_utc'].replace('Z', '+00:00')) == stamp
        assert int(row['particle_id']) == particle['id'] and row['final_status'] == particle['status']
        for key in ('longitude', 'latitude', 'elapsed_seconds'):
            assert float(row[key]) == point[key], f'CSV {key} changed'
    return len(rows)


def particle_csv(raw, module):
    out = module['output']
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
    assert len(rows) == len(out['particles'])
    for row, particle in zip(rows, out['particles']):
        assert row['module'] == module['module'] and row['simulated'] == 'True'
        assert row['method_version'] == METHOD and row['manifest_sha256'] == out['manifest_sha256']
        for key, value in particle.items():
            if key == 'points': continue
            actual = row[key]
            if value is None: assert actual == '', key
            elif isinstance(value, (int, float)): assert float(actual) == value, key
            else: assert actual == value, key
    return len(rows)


def validate_result(actual, expected):
    equivalent(actual, expected)
    assert actual['simulated'] is True and actual['method_version'] == METHOD
    q, summary = actual['query'], actual['summary']
    assert summary['released'] == q['particle_count'] == len(actual['particles'])
    assert sum(summary[name] for name in ('completed', 'left_domain', 'missing_velocity', 'invalid_release')) == summary['released']
    assert actual['total_steps'] == actual['completed_steps'] == q['duration_hours']*3600//q['dt_seconds']
    assert actual['output_interval_seconds'] == math.lcm(1800, q['dt_seconds'])
    start = datetime.fromisoformat(actual['start_time'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(actual['end_time'].replace('Z', '+00:00'))
    assert (end-start).total_seconds() == q['duration_hours']*3600
    assert summary['arrival_fraction'] == summary['arrived']/summary['released'] if q['target_bounds'] else summary['arrival_fraction'] is None
    for p in actual['particles']:
        points = p['points']
        assert points[0] == dict(elapsed_seconds=0, longitude=p['release_longitude'], latitude=p['release_latitude'])
        times = [r['elapsed_seconds'] for r in points]
        assert times == sorted(set(times)) and times[-1] == p['stop_elapsed_seconds']
        assert all(t % actual['output_interval_seconds'] == 0 for t in times[1:-1])
        assert all(math.isfinite(point[key]) for point in points for key in ('longitude', 'latitude'))
        assert p['distance_km'] >= 0
        assert p['arrival_elapsed_seconds'] is None or 0 <= p['arrival_elapsed_seconds'] <= p['stop_elapsed_seconds']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expected-version', default='0.11.1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--records-output', type=Path)
    parser.add_argument('--replay-records', type=Path)
    parser.add_argument('--timeout-seconds', type=float, default=60)
    parser.add_argument('--max-runtime-seconds', type=float, default=900)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 120 or not 30 <= args.max_runtime_seconds <= 1800:
        parser.error('Use a 1-120 second request timeout and 30-1800 second total network budget.')
    started = perf_counter()
    deadline = started + args.max_runtime_seconds
    report = dict(base_url=args.base_url.rstrip('/'), release=args.expected_version, method_version=METHOD,
                  checked_at_utc=datetime.now(timezone.utc).isoformat(), method=__doc__,
                  timeout_seconds=args.timeout_seconds, max_runtime_seconds=args.max_runtime_seconds,
                  retries=0, checks=[], requests=[])
    captures = []
    cases, store = CaseStore(ROOT/'casepacks'), None
    store = DriftStore(cases)

    def request(path, payload=None, status=200, stream=False):
        remaining = deadline-perf_counter()
        assert remaining > 0, 'Whole-run network budget exhausted; no further request sent'
        body = None if payload is None else json.dumps(payload, ensure_ascii=True, allow_nan=False).encode('utf-8')
        entry = dict(path=path, method='GET' if body is None else 'POST', request_sha256=hashlib.sha256(body or b'').hexdigest())
        report['requests'].append(entry)
        began = perf_counter()
        try:
            req = Request(report['base_url']+path, data=body, headers={'Content-Type':'application/json', 'Accept-Encoding':'identity', 'User-Agent':'OceanNavigator-P11-Verifier/1'})
            try: response = urlopen(req, timeout=min(args.timeout_seconds, remaining))
            except HTTPError as error: response = error
            with response:
                headers, actual_status = response.headers, response.status
                if stream and actual_status == 200:
                    lines, events = [], []
                    for line in response:
                        assert perf_counter() < deadline, 'Whole-run deadline exceeded while reading NDJSON'
                        lines.append(line)
                        if line.strip():
                            event = json.loads(line)
                            events.append(event)
                            entry.setdefault('event_arrivals', []).append(dict(type=event['type'], completed_steps=event.get('completed_steps'), seconds=round(perf_counter()-began, 6)))
                    raw = b''.join(lines)
                else: raw = response.read()
            entry.update(status=actual_status, bytes=len(raw), seconds=round(perf_counter()-began, 4), response_sha256=hashlib.sha256(raw).hexdigest())
            assert actual_status == status, f'HTTP {actual_status}, expected {status}: {raw[:200]!r}'
            if path.startswith('/api/'):
                assert headers.get('X-Ocean-App-Version') == args.expected_version, 'Wrong release header'
                assert headers.get('Cache-Control') == ('no-store, no-transform' if stream else 'no-store'), 'Wrong API cache policy'
            if stream:
                assert headers.get('Content-Type', '').startswith('application/x-ndjson')
                assert headers.get('Content-Encoding') in (None, 'identity'), 'NDJSON compressed despite identity request'
                # Vercel may strip upstream-only buffering headers. Record the
                # actual public header without inventing a proxy guarantee.
                entry['stream_headers'] = {k:headers.get(k) for k in ('Content-Type','Content-Encoding','X-Accel-Buffering')}
                return events, headers
            return raw, headers
        except Exception as error:
            entry.update(seconds=round(perf_counter()-began, 4), error=f'{type(error).__name__}: {str(error)[:500]}')
            raise

    def get_json(path, payload=None, status=200):
        return json.loads(request(path, payload, status)[0])

    def check(name, action):
        began = perf_counter()
        try: item = dict(name=name, passed=True, detail=action())
        except Exception as error: item = dict(name=name, passed=False, error=f'{type(error).__name__}: {str(error)[:700]}')
        item['seconds'] = round(perf_counter()-began, 4)
        report['checks'].append(item)
        print(('PASS ' if item['passed'] else 'FAIL ')+name+('' if item['passed'] else ': '+item['error']), flush=True)

    def health():
        body = get_json('/api/health')
        assert body['status'] == 'ok' and body['version'] == args.expected_version and body['case_count'] == 2
        return body
    check('health and release identity', health)

    for case in CASES:
        manifest, digest = cases.require(case)
        report.setdefault('source_identities', {})[case] = digest
        for depth in (0, 32):
            def context(case=case, depth=depth):
                actual = get_json(f'/api/cases/{case}/drift/context?depth_index={depth}&time_index=2')
                expected = store.context(case, depth, 2)
                assert actual == expected, 'Native current coordinates, components, mask or labels changed'
                return dict(depth_m=actual['depth_m'], model_time=actual['model_time'], shape=actual['shape'], manifest_sha256=actual['manifest_sha256'])
            check(f'{case} depth {depth}: exact native current context', context)
            for dt in (300, 600, 1200):
                q = DriftQuery(**query_for(manifest, depth_index=depth, dt_seconds=dt, start_time_index=2, duration_hours=13))
                def stream_run(case=case, q=q):
                    # Stream first, so a prior /run does not warm the same result.
                    events, _ = request(f'/api/cases/{case}/drift/stream', q.model_dump(mode='json'), stream=True)
                    assert events and events[-1]['type'] == 'result'
                    assert all(e['type'] == 'progress' for e in events[:-1])
                    progress = [e['completed_steps'] for e in events[:-1]]
                    total = q.duration_hours*3600//q.dt_seconds
                    assert progress == sorted(set(progress)) and progress[-1] == total
                    # A previously completed warm request may correctly return
                    # one completed-progress event. Cold runs must start at zero.
                    if len(progress)>1:
                        assert progress[0] == 0 and all(b-a <= 12 for a,b in zip(progress, progress[1:]))
                    else: assert progress == [total]
                    actual = get_json(f'/api/cases/{case}/drift/run', q.model_dump(mode='json'))
                    assert events[-1]['result'] == actual, 'Streaming and JSON outputs differ'
                    validate_result(actual, store.run(case, q))
                    return dict(query=q.model_dump(mode='json'), progress_events=len(progress), summary=actual['summary'], output_interval_seconds=actual['output_interval_seconds'], result_sha256=fingerprint(actual))
                check(f'{case} {manifest.coordinates.depth_m[depth]:g} m dt {dt}: NDJSON, JSON and local calculation', stream_run)
        def maximum(case=case, manifest=manifest):
            q = DriftQuery(**query_for(manifest, particle_count=64, duration_hours=72, dt_seconds=300, target_bounds=None))
            actual = get_json(f'/api/cases/{case}/drift/run', q.model_dump(mode='json'))
            validate_result(actual, store.run(case, q))
            assert actual['completed_steps'] == 864 and actual['summary']['released'] == 64
            return dict(summary=actual['summary'], result_sha256=fingerprint(actual), integration_steps=actual['completed_steps'])
        check(f'{case}: maximum supported count, duration and step frequency', maximum)

    def check_zip(saved, raw):
        with ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert {'investigation.json', 'settings.json', 'report.html', 'SOURCES.json', 'source-credits.txt', 'README.txt'} <= set(names)
            current = json.loads(archive.read('investigation.json'))
            validate_bundle(current, args.expected_version)
            assert current['results'] == saved['results'] and current['replay'] == saved['replay']
            assert json.loads(archive.read('settings.json')) == saved['replay']
            assert json.loads(archive.read('SOURCES.json')) == current['references']
            html = archive.read('report.html').decode('utf-8')
            assert 'Historical investigation' in html and '<script' not in html.lower()
            assert 'HYCOM' in archive.read('source-credits.txt').decode('utf-8')
            csv_rows = {}
            for module in saved['results']:
                if module['module'] not in ('drift_run', 'reference_drift_run'): continue
                prefix = 'drift' if module['module'] == 'drift_run' else 'reference-drift'
                csv_rows[prefix+'-trajectories.csv'] = trajectory_csv(archive.read(prefix+'-trajectories.csv'), module)
                csv_rows[prefix+'-particles.csv'] = particle_csv(archive.read(prefix+'-particles.csv'), module)
            return dict(files=names, csv_rows=csv_rows, result_sha256=current['result_sha256'])

    for case in CASES:
        manifest, digest = cases.require(case)
        for variant in ('point', 'deep', 'last-available-window', 'comparison'):
            q = query_for(manifest)
            comparison = None
            if variant == 'point':
                b = q['release']['bounds']
                q.update(release=dict(kind='point', longitude=(b[0]+b[2])/2, latitude=(b[1]+b[3])/2), dt_seconds=300)
            elif variant == 'deep': q.update(depth_index=32, dt_seconds=1200)
            elif variant == 'last-available-window': q.update(start_time_index=5, duration_hours=12, target_bounds=None)
            else: comparison = {**q, 'depth_index':32, 'start_time_index':3, 'dt_seconds':300, 'seed':1821}
            recipe = dict(mode='drift', case_id=case, query=q, comparison=comparison)
            title = f'P11 {case} {variant} <script>'
            before = len(captures)
            def capture(recipe=recipe, title=title, digest=digest):
                record = get_json('/api/investigations/capture', dict(title=title, recipe=recipe, expected_model_sha256=digest))
                validate_bundle(record, args.expected_version)
                assert record['replay']['sources']['methods']['drift'] == METHOD
                expected_names = ['drift_run']+(['reference_drift_run'] if recipe['comparison'] else [])
                assert [m['module'] for m in record['results']] == expected_names
                for index, module in enumerate(record['results']):
                    expected_query = recipe['comparison'] if index else recipe['query']
                    assert module['parameters'] == expected_query and module['random_seed'] == expected_query['seed']
                    validate_result(module['output'], store.run(recipe['case_id'], DriftQuery(**expected_query)))
                assert len(record['references'][0]['files']) == 7
                captures.append(record)
                return dict(modules=expected_names, result_sha256=record['result_sha256'])
            check(f'capture {case} {variant}', capture)
            if len(captures) == before: continue
            saved = captures[-1]
            def replay(saved=saved):
                record = get_json('/api/investigations/replay', saved['replay'])
                validate_bundle(record, args.expected_version)
                assert record['results'] == saved['results'] and record['replay'] == saved['replay']
                return dict(result_sha256=record['result_sha256'])
            check(f'exact replay {case} {variant}', replay)
            check(f'evidence ZIP {case} {variant}', lambda saved=saved: check_zip(saved, request('/api/investigations/export', dict(replay=saved['replay'], format='zip'))[0]))
            if variant == 'comparison':
                def direct_exports(saved=saved):
                    raw, headers = request('/api/investigations/export', dict(replay=saved['replay'], format='csv'))
                    rows = trajectory_csv(raw, saved['results'][0])
                    assert 'drift-trajectories.csv' in headers.get('Content-Disposition', '')
                    html = request('/api/investigations/export', dict(replay=saved['replay'], format='html'))[0].decode('utf-8')
                    assert '&lt;script&gt;' in html and '<script' not in html.lower() and 'real-world probabilities' in html
                    assert 'Twelve-hourly source snapshots' in html and 'Reference drift run' in html
                    return dict(primary_csv_rows=rows, report_retains_methods_and_limits=True)
                check(f'direct CSV and escaped HTML {case}', direct_exports)

    record_sets = [('original P08', ROOT/'docs/evidence/p08-local-records.json'),
                   ('original P10', ROOT/'docs/evidence/p10-v2-local-records.json')]
    if args.replay_records: record_sets.append(('separate process P11', args.replay_records))
    for label, path in record_sets:
        records = read_records(path)
        report.setdefault('replay_reference_files', []).append(dict(label=label, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), records=len(records)))
        for index, saved in enumerate(records):
            def old_replay(saved=saved):
                record = get_json('/api/investigations/replay', saved['replay'])
                validate_bundle(record, args.expected_version)
                assert record['results'] == saved['results'] and record['replay'] == saved['replay']
                assert record['result_sha256'] == saved['result_sha256']
                return dict(mode=record['replay']['recipe']['mode'], modules=len(record['results']), result_sha256=record['result_sha256'])
            check(f'{label} record {index+1}: exact replay', old_replay)
            if label == 'separate process P11':
                check(f'{label} record {index+1}: exact exported archive', lambda saved=saved: check_zip(saved, request('/api/investigations/export', dict(replay=saved['replay'], format='zip'))[0]))

    q = query_for(cases.require(CASES[0])[0])
    base = f'/api/cases/{CASES[0]}/drift/'
    guards = [
        ('zero particles', {'particle_count':0}, 'invalid_request'),
        ('excess particles', {'particle_count':65}, 'invalid_request'),
        ('fractional duration', {'duration_hours':1.5}, 'invalid_request'),
        ('excess duration', {'duration_hours':73}, 'invalid_request'),
        ('unsupported step', {'dt_seconds':60}, 'invalid_request'),
        ('unsupported depth', {'depth_index':33}, 'invalid_request'),
        ('extra property', {'vertical_velocity':1}, 'invalid_request'),
        ('malformed coordinate', {'release':dict(kind='point', longitude='not longitude', latitude=13)}, 'invalid_request'),
        ('nonfinite coordinate', {'release':dict(kind='point', longitude='NaN', latitude=13)}, 'invalid_request'),
        ('outside release', {'release':dict(kind='point', longitude=0, latitude=0)}, 'outside_coverage'),
        ('reversed release box', {'release':dict(kind='box', bounds=[89,14,86,13])}, 'outside_coverage'),
        ('empty target', {'target_bounds':[86,13,86,14]}, 'invalid_target'),
        ('forcing exhausted', {'start_time_index':6,'duration_hours':1}, 'forcing_exhausted'),
        ('duration cannot be silently shortened', {'start_time_index':5,'duration_hours':13}, 'forcing_exhausted'),
    ]
    for name, patch, code in guards:
        def guard(patch=patch, code=code):
            response = get_json(base+'run', {**q,**patch}, 422)
            assert response['error']['code'] == code
            return dict(error_code=code)
        check('reject '+name, guard)
    def invalid_stream():
        response = get_json(base+'stream', {**q,'start_time_index':6}, 422)
        assert response['error']['code'] == 'forcing_exhausted'
        return dict(error_code=response['error']['code'])
    check('invalid stream rejected before response begins', invalid_stream)
    if captures:
        for kind in ('source','method','recipe','result'):
            def mismatch(kind=kind):
                replay = deepcopy(captures[0]['replay'])
                if kind == 'source': replay['sources']['model_manifest_sha256'] = '0'*64
                elif kind == 'method': replay['sources']['methods']['drift'] = 'unsupported-drift-v99'
                elif kind == 'recipe': replay['recipe']['query']['seed'] += 1
                else: replay['expected_result_sha256'] = '0'*64
                if kind in ('source','method'): replay['expected_recipe_sha256'] = fingerprint(dict(recipe=replay['recipe'], sources=replay['sources']))
                response = get_json('/api/investigations/replay', replay, 422)
                assert response['error']['code'] == kind+'_mismatch'
                return dict(error_code=response['error']['code'])
            check('reject saved '+kind+' mismatch', mismatch)
        def identical():
            recipe = dict(mode='drift', case_id=CASES[0], query=q, comparison=q)
            response = get_json('/api/investigations/capture', dict(title='Invalid identical comparison', recipe=recipe), 422)
            assert response['error']['code'] == 'invalid_request'
            return dict(error_code='invalid_request')
        check('reject identical comparison recipe', identical)

    for filename in ('p11-api-local-records.json', 'p11-api-public-records.json'):
        def legacy_method(filename=filename):
            old = read_records(ROOT/'docs/evidence'/filename)[0]
            assert old['replay']['sources']['methods']['drift'] == 'p11-drift-v1'
            response = get_json('/api/investigations/replay', old['replay'], 422)
            assert response['error']['code'] == 'method_mismatch'
            return dict(archive=filename, error_code='method_mismatch')
        check('initial method archive remains explicitly unsupported: '+filename, legacy_method)

    for path, tokens in (('/',('Depth Atlas',)),('/privacy',('Privacy',)),('/terms',('Terms',)),('/favicon.svg',('<svg',)),('/third-party-notices.txt',('HYCOM','Argo','Natural Earth'))):
        def static(path=path, tokens=tokens):
            raw, headers = request(path)
            text = raw.decode('utf-8')
            assert all(token in text for token in tokens)
            return dict(bytes=len(raw), content_type=headers.get('Content-Type'), sha256=hashlib.sha256(raw).hexdigest())
        check('public document '+path, static)
    if args.records_output:
        args.records_output.parent.mkdir(parents=True, exist_ok=True)
        args.records_output.write_text(json.dumps(dict(schema_version='p11-verification-records-v1', base_url=report['base_url'], release=args.expected_version, records=captures), ensure_ascii=True, allow_nan=False)+'\n', encoding='utf-8')
        report['records_written'] = dict(path=str(args.records_output), count=len(captures), sha256=hashlib.sha256(args.records_output.read_bytes()).hexdigest())
    report['passed_checks'] = sum(item['passed'] for item in report['checks'])
    report['failed_checks'] = len(report['checks'])-report['passed_checks']
    report['passed'] = not report['failed_checks']
    report['request_count'] = len(report['requests'])
    report['elapsed_seconds'] = round(perf_counter()-started, 4)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('passed','passed_checks','failed_checks','request_count','elapsed_seconds')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
