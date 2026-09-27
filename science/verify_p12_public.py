"""Bounded P12 HTTP, source transport, replay and evidence export acceptance.

Local calculations check deployment consistency, not independent ocean truth.
Independent reference-code, original-source and analytical checks are in
tests/test_heat_independent.py. Requests never retry automatically. Each request
and the complete run have explicit budgets; failures remain in the report.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
from datetime import date, datetime, timezone
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
from api.heat_store import HeatStore
from api.instrument_store import InstrumentStore
from science.heat_contracts import HeatQuery, METHOD
from science.verify_p10_public import equivalent, fingerprint, validate_bundle
from science.verify_p11_public import read_records

CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')


def cell_equals(actual, expected):
    if expected is None:
        assert actual == '', f'Missing CSV value became {actual!r}'
    elif isinstance(expected, bool):
        assert actual == str(expected)
    elif isinstance(expected, (int, float)):
        assert float(actual) == expected, f'CSV numerical value changed: {actual!r} != {expected!r}'
    elif isinstance(expected, (dict, list)):
        assert json.loads(actual) == expected
    else:
        assert actual == expected


def check_csv(raw, expected_rows, metadata):
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
    assert len(rows) == len(expected_rows), 'CSV row count changed'
    for actual, expected in zip(rows, expected_rows):
        for key, value in {**metadata, **expected}.items():
            assert key in actual, f'Missing CSV field {key}'
            cell_equals(actual[key], value)
    return len(rows)


def surface_metadata(output):
    return dict(method_version=METHOD, case_id=output['case_id'], location_id=output['location']['id'],
                longitude_deg_east=output['location']['longitude'], latitude_deg_north=output['location']['latitude'],
                heat_manifest_sha256=output['heat_manifest_sha256'],
                baseline_start_year=1982, baseline_end_year=2011)


def check_heat_archive(raw, saved, version):
    with ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        required = {'investigation.json', 'settings.json', 'SOURCES.json', 'report.html', 'source-credits.txt',
                    'README.txt', 'heat-surface-series.csv', 'heat-events.csv', 'heat-climatology.csv'}
        assert required <= set(names)
        current = json.loads(archive.read('investigation.json'))
        validate_bundle(current, version)
        assert current['results'] == saved['results'] and current['replay'] == saved['replay']
        assert json.loads(archive.read('settings.json')) == saved['replay']
        assert json.loads(archive.read('SOURCES.json')) == saved['references']
        html = archive.read('report.html').decode('utf-8')
        assert '<script' not in html.lower() and 'Historical investigation' in html
        assert '1982' in html and '2011' in html and 'subsurface' in html
        credits = archive.read('source-credits.txt').decode('utf-8')
        assert 'HYCOM' in credits and 'OISST' in credits
        output = saved['results'][0]['output']
        metadata = surface_metadata(output)
        counts = {'heat-surface-series.csv': check_csv(archive.read('heat-surface-series.csv'), output['series'], metadata)}
        # CSV intentionally omits display-year edge flags, retained in JSON.
        event_rows = [{k:v for k,v in event.items() if k not in ('starts_before_year', 'ends_after_year')}
                      for event in output['events']]
        counts['heat-events.csv'] = check_csv(archive.read('heat-events.csv'), event_rows, metadata)
        climatology_rows = [dict(leap_calendar_day_1_based=i+1, seasonal_mean_c=output['baseline']['seasonal_mean_c'][i],
                                 threshold_c=output['baseline']['threshold_c'][i], unsmoothed_pool_count=output['baseline']['pool_count'][i])
                            for i in range(366)]
        counts['heat-climatology.csv'] = check_csv(archive.read('heat-climatology.csv'), climatology_rows, metadata)
        profile = output['depth_profile']
        depth_names = {'heat-depth-profile.csv', 'heat-depth-layers.csv', 'heat-depth-integral.csv', 'heat-mixed-layer.csv'}
        if profile is None:
            assert not depth_names.intersection(names), 'Unavailable depth evidence acquired fabricated CSV tables'
        else:
            assert depth_names <= set(names)
            metadata = dict(method_version=METHOD, model_manifest_sha256=output['model_manifest_sha256'],
                            model_time_utc=profile['model_time'], model_longitude_deg_east=profile['longitude'],
                            model_latitude_deg_north=profile['latitude'], depth_limit_m=profile['depth_limit_m'])
            for name, rows in [('heat-depth-profile.csv', profile['points']), ('heat-depth-layers.csv', profile['layers']),
                               ('heat-depth-integral.csv', [profile['heat_content']]),
                               ('heat-mixed-layer.csv', [dict(criterion=k, **v) for k,v in profile['mixed_layer'].items()])]:
                counts[name] = check_csv(archive.read(name), rows, metadata)
        return dict(files=names, csv_rows=counts, result_sha256=current['result_sha256'])


def validate_analysis(actual, expected, cases, store):
    equivalent(actual, expected)
    assert actual['method_version'] == METHOD and actual['kind'] == 'derived'
    manifest, model_sha = cases.require(actual['case_id'])
    heat_manifest, heat_sha = store.manifest()
    assert actual['model_manifest_sha256'] == model_sha and actual['heat_manifest_sha256'] == heat_sha
    assert actual['source'] == heat_manifest['source'], 'Provider URL, version or metadata changed in transport'
    source = store.source_series(actual['case_id'], actual['location']['id'])
    source_by_day = dict(zip(source['dates'], source['sst_c']))
    year = actual['query']['year']
    assert len(actual['series']) == (366 if year == 2024 else 365)
    assert actual['series'][0]['date'] == f'{year}-01-01' and actual['series'][-1]['date'] == f'{year}-12-31'
    for row in actual['series']:
        assert row['sst_c'] == source_by_day[row['date']], 'Source SST changed in transport'
        if row['sst_c'] is None:
            assert row['anomaly_c'] is None and row['exceeds_threshold'] is None and row['event_id'] is None
        else:
            assert row['exceeds_threshold'] == (row['sst_c'] > row['threshold_c'])
            assert row['anomaly_c'] == row['sst_c']-row['seasonal_mean_c']
    for event in actual['events']:
        assert event['duration_days'] == (date.fromisoformat(event['end'])-date.fromisoformat(event['start'])).days+1
        assert event['exceedance_days']+event['bridged_days'] == event['duration_days']
        assert event['complete_boundaries'] == (not event['left_boundary_unknown'] and not event['right_boundary_unknown'])
        assert event['depth_overlap'] == any(event['start'] <= value[:10] <= event['end'] for value in manifest.coordinates.times)
    profile = actual['depth_profile']
    if profile is None:
        assert actual['depth_link']['status'] != 'available'
        return
    assert actual['depth_link']['status'] == 'available'
    assert actual['selected_event']['start'] <= profile['model_time'][:10] <= actual['selected_event']['end']
    assert profile['model_time'] == manifest.coordinates.times[actual['query']['model_time_index']]
    coordinates = manifest.coordinates
    yi, xi = profile['latitude_index'], profile['longitude_index']
    assert profile['latitude'] == coordinates.latitude[yi] and profile['longitude'] == coordinates.longitude[xi]
    offset, width = yi*len(coordinates.longitude)+xi, len(coordinates.longitude)*len(coordinates.latitude)
    for variable, key in [('temperature', 'in_situ_temperature_c'), ('salinity', 'practical_salinity')]:
        native = cases._read_array(actual['case_id'], 'analytical', variable, actual['query']['model_time_index'])
        for point in profile['points']:
            assert point['depth_m'] == coordinates.depth_m[point['index']]
            value = native[point['index']*width+offset]
            assert point[key] == (float(value) if math.isfinite(value) else None)
    assert profile['points'][-1]['depth_m'] == actual['query']['depth_limit_m']
    heat = profile['heat_content']
    assert heat['reference_conservative_temperature_c'] == 0 and heat['cp0_j_kg_k'] == 3991.86795711963
    if heat['status'] == 'available':
        assert all(point['status'] == 'valid' for point in profile['points'])
        assert heat['value_gj_m2'] == heat['value_j_m2']/1e9


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expected-version', default='0.12.0')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--records-output', type=Path)
    parser.add_argument('--replay-records', type=Path)
    parser.add_argument('--replay-only', action='store_true',
                        help='Check only source identity, supplied exact replays and their evidence ZIPs.')
    parser.add_argument('--timeout-seconds', type=float, default=60)
    parser.add_argument('--max-runtime-seconds', type=float, default=900)
    args = parser.parse_args()
    if args.replay_only and not args.replay_records:
        parser.error('--replay-only requires --replay-records.')
    if not 1 <= args.timeout_seconds <= 120 or not 30 <= args.max_runtime_seconds <= 1800:
        parser.error('Use a 1-120 second request timeout and a 30-1800 second run budget.')
    started = perf_counter()
    deadline = started+args.max_runtime_seconds
    report = dict(base_url=args.base_url.rstrip('/'), release=args.expected_version, method_version=METHOD,
                  checked_at_utc=datetime.now(timezone.utc).isoformat(), method=__doc__, retries=0,
                  timeout_seconds=args.timeout_seconds, max_runtime_seconds=args.max_runtime_seconds,
                  checks=[], requests=[], complete=False)
    captures, catalogues = [], {}
    cases = CaseStore(ROOT/'casepacks')
    store = HeatStore(cases, InstrumentStore(ROOT/'casepacks/instruments'))

    def save_report():
        report['passed_checks'] = sum(item['passed'] for item in report['checks'])
        report['failed_checks'] = len(report['checks'])-report['passed_checks']
        report['passed'] = report['complete'] and not report['failed_checks']
        report['request_count'] = len(report['requests'])
        report['elapsed_seconds'] = round(perf_counter()-started, 4)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False)+'\n', encoding='utf-8')

    def request(path, payload=None, status=200):
        remaining = deadline-perf_counter()
        assert remaining > 0, 'Whole-run network budget exhausted; no request sent'
        body = None if payload is None else json.dumps(payload, ensure_ascii=True, allow_nan=False).encode('utf-8')
        entry = dict(path=path, method='GET' if body is None else 'POST', request_sha256=hashlib.sha256(body or b'').hexdigest())
        report['requests'].append(entry)
        began = perf_counter()
        try:
            req = Request(report['base_url']+path, data=body, headers={'Content-Type':'application/json', 'Accept-Encoding':'identity', 'User-Agent':'OceanNavigator-P12-Verifier/1'})
            try:
                response = urlopen(req, timeout=min(args.timeout_seconds, remaining))
            except HTTPError as error:
                response = error
            with response:
                headers, actual_status = response.headers, response.status
                chunks, size = [], 0
                while True:
                    assert perf_counter() < deadline, 'Whole-run budget exceeded while reading response'
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    assert size <= 8*1024*1024, 'Response exceeds bounded 8 MB verifier limit'
                raw = b''.join(chunks)
            entry.update(status=actual_status, bytes=len(raw), seconds=round(perf_counter()-began, 4), response_sha256=hashlib.sha256(raw).hexdigest())
            assert actual_status == status, f'HTTP {actual_status}, expected {status}: {raw[:250]!r}'
            if path.startswith('/api/'):
                assert headers.get('X-Ocean-App-Version') == args.expected_version, 'Wrong release header'
                assert headers.get('Cache-Control') == 'no-store', 'Wrong API cache policy'
            return raw, headers
        except Exception as error:
            entry.update(seconds=round(perf_counter()-began, 4), error=f'{type(error).__name__}: {str(error)[:500]}')
            raise

    def get_json(path, payload=None, status=200):
        return json.loads(request(path, payload, status)[0])

    def check(name, action):
        began = perf_counter()
        try:
            item = dict(name=name, passed=True, detail=action())
        except Exception as error:
            item = dict(name=name, passed=False, error=f'{type(error).__name__}: {str(error)[:900]}')
        item['seconds'] = round(perf_counter()-began, 4)
        report['checks'].append(item)
        save_report()
        print(('PASS ' if item['passed'] else 'FAIL ')+name+('' if item['passed'] else ': '+item['error']), flush=True)
        return item['passed']

    def health():
        body = get_json('/api/health')
        assert body['status'] == 'ok' and body['version'] == args.expected_version and body['case_count'] == 2
        return body
    check('health and release identity', health)

    def local_sources():
        manifest, digest = store.manifest()
        assert len(manifest['locations']) == 6 and manifest['baseline_period'] == [1982, 2011]
        for location in manifest['locations']:
            store.source_series(location['case_id'], location['id'])
        report['source_identities'] = dict(heat_manifest_sha256=digest, source=manifest['source'],
                                          models={case:cases.require(case)[1] for case in CASES})
        return dict(heat_manifest_sha256=digest, checked_locations=6)
    if not check('local immutable source identities available', local_sources):
        report['complete'] = True
        save_report()
        return 1

    if args.replay_only:
        records = []
        def load_replay_only():
            records.extend(read_records(args.replay_records))
            assert len(records) == 8, 'Expected the eight declared P12 cross-process records'
            assert all(record['replay']['recipe']['mode'] == 'heat' for record in records)
            report['replay_reference_files'] = [dict(path=str(args.replay_records),
                sha256=hashlib.sha256(args.replay_records.read_bytes()).hexdigest(), records=len(records))]
            return dict(records=len(records))
        if check('separate process P12: eight retained reference records available', load_replay_only):
            for index, saved in enumerate(records):
                def exact(saved=saved):
                    actual = get_json('/api/investigations/replay', saved['replay'])
                    validate_bundle(actual, args.expected_version)
                    assert actual['results'] == saved['results'] and actual['replay'] == saved['replay']
                    assert actual['result_sha256'] == saved['result_sha256']
                    return dict(result_sha256=actual['result_sha256'], query=actual['replay']['recipe']['query'])
                check(f'separate process P12 {index+1}: exact replay', exact)
                check(f'separate process P12 {index+1}: exact exported evidence',
                      lambda saved=saved: check_heat_archive(request('/api/investigations/export',
                          dict(replay=saved['replay'], format='zip'))[0], saved, args.expected_version))
        report['complete'] = True
        save_report()
        print(json.dumps({key: report[key] for key in ('passed', 'passed_checks', 'failed_checks', 'request_count', 'elapsed_seconds')}))
        return 0 if report['passed'] else 1

    endpoint_outputs = {}
    for case in CASES:
        def catalog(case=case):
            actual = get_json(f'/api/cases/{case}/heat/catalog')
            assert actual == store.catalog(case), 'Catalogue coordinates, source metadata, method or defaults changed'
            catalogues[case] = actual
            return dict(locations=[p['id'] for p in actual['locations']], source=actual['source'])
        check(f'{case}: complete catalogue and source URL identity', catalog)
        for location in store.catalog(case)['locations']:
            for year in (2023, 2024):
                query = HeatQuery(location_id=location['id'], year=year)
                def analyse(case=case, query=query):
                    actual = get_json(f'/api/cases/{case}/heat/analyse', query.model_dump(mode='json'))
                    validate_analysis(actual, store.analyse(case, query), cases, store)
                    endpoint_outputs[(case, query.location_id, query.year)] = actual
                    return dict(events=len(actual['events']), selected_event=actual['query']['event_id'],
                                depth_status=actual['depth_link']['status'], result_sha256=fingerprint(actual))
                check(f'{case} {location["id"]} {year}: seasonal events and exact native source values', analyse)

    # Select an already declared location that offers depth support for the
    # diagnostic check. This does not change the source acquisition recipe.
    supported_queries = {}
    for case in CASES:
        candidates = [store.analyse(case, HeatQuery(location_id=p['id'], year=2024)) for p in store.catalog(case)['locations']]
        supported = next((out for out in candidates if out['depth_profile'] is not None), None)
        if supported:
            supported_queries[case] = supported['query']
            for limit in (100, 300, 700, 1000):
                query = HeatQuery(**{**supported['query'], 'depth_limit_m':limit})
                def depth(case=case, query=query):
                    actual = get_json(f'/api/cases/{case}/heat/analyse', query.model_dump(mode='json'))
                    validate_analysis(actual, store.analyse(case, query), cases, store)
                    assert actual['depth_profile'] is not None
                    return dict(query=actual['query'], heat_content=actual['depth_profile']['heat_content'], mixed_layer=actual['depth_profile']['mixed_layer'])
                check(f'{case}: native diagnostics and integration to {limit} m', depth)
    def depth_supported():
        assert supported_queries, 'No real event-period profile was exercised; depth feature acceptance remains open'
        return dict(cases_with_event_depth_support=list(supported_queries), note='Other locations and years retain their real unavailable states.')
    check('real source context exercises the depth feature', depth_supported)

    for case in CASES:
        default = supported_queries.get(case, store.catalog(case)['default_query'])
        for variant, year, limit, time_index in [('shallow',2024,100,0), ('medium',2024,300,2), ('historical-year',2023,700,4), ('deep',2024,1000,6)]:
            query = HeatQuery(**{**default, 'year':year, 'depth_limit_m':limit, 'model_time_index':time_index, 'event_id':None})
            # Capture requires the resolved applied event, not a draft default.
            query = HeatQuery(**store.analyse(case, query)['query'])
            recipe = dict(mode='heat', case_id=case, query=query.model_dump(mode='json'))
            before = len(captures)
            def capture(case=case, recipe=recipe, variant=variant):
                record = get_json('/api/investigations/capture', dict(title=f'P12 {case} {variant} <script>', recipe=recipe,
                                  expected_model_sha256=cases.require(case)[1], expected_heat_manifest_sha256=store.manifest()[1]))
                validate_bundle(record, args.expected_version)
                assert record['replay']['sources']['methods']['heat'] == METHOD
                assert record['replay']['sources']['heat_manifest_sha256'] == store.manifest()[1]
                assert [m['module'] for m in record['results']] == ['heat_analysis']
                module = record['results'][0]
                assert module['method_version'] == METHOD and module['random_seed'] is None
                expected = store.analyse(case, HeatQuery(**recipe['query']))
                validate_analysis(module['output'], expected, cases, store)
                assert module['parameters'] == expected['query']
                assert any(ref.get('source_url') == store.manifest()[0]['source']['source_url'] for ref in record['references'])
                captures.append(record)
                return dict(result_sha256=record['result_sha256'], query=module['parameters'], depth_status=module['output']['depth_link']['status'])
            check(f'capture {case} {variant}', capture)
            if len(captures) == before:
                continue
            saved = captures[-1]
            def replay(saved=saved):
                actual = get_json('/api/investigations/replay', saved['replay'])
                validate_bundle(actual, args.expected_version)
                assert actual['results'] == saved['results'] and actual['replay'] == saved['replay']
                return dict(result_sha256=actual['result_sha256'])
            check(f'exact replay {case} {variant}', replay)
            check(f'evidence ZIP {case} {variant}', lambda saved=saved: check_heat_archive(request('/api/investigations/export', dict(replay=saved['replay'], format='zip'))[0], saved, args.expected_version))
            if variant == 'deep':
                def direct_exports(saved=saved):
                    raw, headers = request('/api/investigations/export', dict(replay=saved['replay'], format='csv'))
                    out = saved['results'][0]['output']
                    count = check_csv(raw, out['series'], surface_metadata(out))
                    assert 'heat-surface-series.csv' in headers.get('Content-Disposition', '')
                    html = request('/api/investigations/export', dict(replay=saved['replay'], format='html'))[0].decode('utf-8')
                    assert '&lt;script&gt;' in html and '<script' not in html.lower()
                    assert '1982' in html and '2011' in html and 'subsurface' in html and 'potential-enthalpy' in html
                    return dict(surface_rows=count, escaped_report=True)
                check(f'direct source CSV and escaped report {case}', direct_exports)

    record_sets = [('original P08', ROOT/'docs/evidence/p08-local-records.json'),
                   ('original P10', ROOT/'docs/evidence/p10-v2-local-records.json'),
                   ('original P11', ROOT/'docs/evidence/p11-v2-local-records.json')]
    if args.replay_records:
        record_sets.append(('separate process P12', args.replay_records))
    for label, path in record_sets:
        loaded = []
        def load_records(path=path):
            loaded.extend(read_records(path))
            assert loaded
            report.setdefault('replay_reference_files', []).append(dict(label=label, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), records=len(loaded)))
            return dict(records=len(loaded))
        if not check(label+': retained reference records available', load_records):
            continue
        for index, saved in enumerate(loaded):
            def old_replay(saved=saved):
                record = get_json('/api/investigations/replay', saved['replay'])
                validate_bundle(record, args.expected_version)
                assert record['results'] == saved['results'] and record['replay'] == saved['replay']
                assert record['result_sha256'] == saved['result_sha256']
                return dict(mode=record['replay']['recipe']['mode'], result_sha256=record['result_sha256'])
            check(f'{label} {index+1}: exact replay', old_replay)
            if label == 'separate process P12':
                check(f'{label} {index+1}: exact exported evidence', lambda saved=saved: check_heat_archive(request('/api/investigations/export', dict(replay=saved['replay'], format='zip'))[0], saved, args.expected_version))

    base_query = store.catalog(CASES[0])['default_query']
    for name, patch, code in [
        ('unsupported year', {'year':2022}, 'invalid_request'),
        ('unsupported depth', {'depth_limit_m':200}, 'invalid_request'),
        ('excess model index', {'model_time_index':7}, 'invalid_request'),
        ('fractional model index', {'model_time_index':1.5}, 'invalid_request'),
        ('extra setting', {'forecast':True}, 'invalid_request'),
        ('unregistered location', {'location_id':'unknown'}, 'unsupported_heat_location'),
        ('other case location', {'location_id':'arabian-center'}, 'unsupported_heat_location'),
        ('unregistered event', {'event_id':'mhw-2024-01-01-2024-01-02'}, 'unsupported_heat_event'),
    ]:
        def guard(patch=patch, code=code):
            result = get_json(f'/api/cases/{CASES[0]}/heat/analyse', {**base_query, **patch}, 422)
            assert result['error']['code'] == code
            return dict(error_code=code)
        check('reject '+name, guard)
    if captures:
        for kind in ('source', 'heat_source', 'method', 'recipe', 'result'):
            def mismatch(kind=kind):
                replay = deepcopy(captures[0]['replay'])
                if kind == 'source': replay['sources']['model_manifest_sha256'] = '0'*64
                elif kind == 'heat_source': replay['sources']['heat_manifest_sha256'] = '0'*64
                elif kind == 'method': replay['sources']['methods']['heat'] = 'unsupported-heat-v99'
                elif kind == 'recipe': replay['recipe']['query']['depth_limit_m'] = 1000
                else: replay['expected_result_sha256'] = '0'*64
                if kind in ('source', 'heat_source', 'method'):
                    replay['expected_recipe_sha256'] = fingerprint(dict(recipe=replay['recipe'], sources=replay['sources']))
                response = get_json('/api/investigations/replay', replay, 422)
                code = ('source' if kind == 'heat_source' else kind)+'_mismatch'
                assert response['error']['code'] == code
                return dict(error_code=code)
            check('reject saved '+kind+' mismatch', mismatch)
    for path, tokens in [('/', ('Depth Atlas',)), ('/privacy', ('Privacy',)), ('/terms', ('Terms',)),
                         ('/favicon.svg', ('<svg',)), ('/third-party-notices.txt', ('HYCOM', 'Argo', 'OISST'))]:
        def static(path=path, tokens=tokens):
            raw, headers = request(path)
            assert all(token in raw.decode('utf-8') for token in tokens)
            return dict(bytes=len(raw), content_type=headers.get('Content-Type'), sha256=hashlib.sha256(raw).hexdigest())
        check('public document '+path, static)
    if args.records_output:
        args.records_output.parent.mkdir(parents=True, exist_ok=True)
        args.records_output.write_text(json.dumps(dict(schema_version='p12-verification-records-v1', base_url=report['base_url'], release=args.expected_version, records=captures), ensure_ascii=True, allow_nan=False)+'\n', encoding='utf-8')
        report['records_written'] = dict(path=str(args.records_output), count=len(captures), sha256=hashlib.sha256(args.records_output.read_bytes()).hexdigest())
    report['complete'] = True
    save_report()
    print(json.dumps({key:report[key] for key in ('passed', 'passed_checks', 'failed_checks', 'request_count', 'elapsed_seconds')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
