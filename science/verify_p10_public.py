"""P10 deployment, numerical transport, saved-record and export checks.

Expected endpoint outputs are calculated in a separate local process from the
checked case packs. This is deployment consistency evidence. Independent science
is checked separately by tests/test_expedition_independent.py using original
provider files and a different distance/IDW oracle. HTTP failures are retained;
there are no retries and every request uses the same fixed 60-second timeout.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASE_IDS = ('bay-bengal-2024-01', 'arabian-sea-2024-01')
DEFAULT = dict(variable='temperature', depth_index=0, budget=8, min_spacing_km=30, objective='gradient', seed=26067)
CSV_FILES = {'station_plan': ('stations.csv', 'stations'), 'virtual_survey': ('simulated-survey.csv', 'samples'),
             'sampling_experiment': ('reconstruction-benchmark.csv', 'runs')}


def fingerprint(value):
    """Separate implementation of the published portable numeric hash format."""
    def tag(v):
        if v is None: return ['null']
        if isinstance(v, bool): return ['boolean', v]
        if isinstance(v, (float, int)):
            assert math.isfinite(v) and (not isinstance(v, int) or abs(v) <= 2**53 - 1)
            return ['number', struct.pack('>d', float(v) if v else 0.).hex()]
        if isinstance(v, str): return ['string', v]
        if isinstance(v, (tuple, list)): return ['array', [tag(item) for item in v]]
        assert isinstance(v, dict) and all(isinstance(k, str) for k in v)
        return ['object', [[key, tag(v[key])] for key in sorted(v)]]
    return hashlib.sha256(json.dumps(tag(value), ensure_ascii=True, separators=(',', ':')).encode('ascii')).hexdigest()


def equivalent(actual, expected, path='$'):
    """Transport tolerance only; replay hashes and saved outputs remain exact."""
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        assert actual == expected and type(actual) is type(expected), f'{path}: {actual!r} != {expected!r}'
    elif isinstance(expected, (float, int)):
        assert isinstance(actual, (float, int)) and not isinstance(actual, bool), path
        assert math.isfinite(actual) and math.isclose(actual, expected, rel_tol=2e-12, abs_tol=2e-12), f'{path}: {actual!r} != {expected!r}'
    elif isinstance(expected, (tuple, list)):
        assert isinstance(actual, list) and len(actual) == len(expected), f'{path}: list length'
        for index, (a, b) in enumerate(zip(actual, expected)): equivalent(a, b, f'{path}[{index}]')
    else:
        assert isinstance(actual, dict) and set(actual) == set(expected), f'{path}: keys'
        for key, value in expected.items(): equivalent(actual[key], value, f'{path}.{key}')


def validate_bundle(record, version):
    assert record['kind'] == 'ocean_investigation' and record['software']['app'] == version
    assert fingerprint({k: v for k, v in record.items() if k != 'document_sha256'}) == record['document_sha256']
    assert fingerprint(record['results']) == record['result_sha256'] == record['replay']['expected_result_sha256']
    assert fingerprint(dict(recipe=record['replay']['recipe'], sources=record['replay']['sources'])) == record['replay']['expected_recipe_sha256']
    for module in record['results']:
        assert fingerprint(module['output']) == module['output_sha256']


def csv_equal(raw, output, collection):
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
    source_rows = output[collection]
    module_name = next(name for name, (_, field) in CSV_FILES.items() if field == collection)
    assert len(rows) == len(source_rows)
    for actual, source in zip(rows, source_rows):
        assert actual['module'] == module_name
        assert actual['method_version'] == output['method_version']
        assert actual['manifest_sha256'] == output['manifest_sha256']
        assert actual['simulated'] == str(module_name in ('virtual_survey', 'sampling_experiment'))
        # A survey may sample a different time from the frozen planning prior.
        # Benchmark rows carry their own held-out snapshot time.
        expected_time = (output['model_time'] if module_name == 'virtual_survey'
                         else source['model_time'] if module_name == 'sampling_experiment'
                         else output['prior_time'])
        assert actual['sample_time_utc'] == expected_time, 'CSV sample time differs from actual sampled snapshot'
        for key, value in {k: output[k] for k in ('case_id', 'variable', 'units', 'depth_m', 'prior_time')}.items():
            assert float(actual[key]) == value if isinstance(value, (float, int)) else actual[key] == value
        for key, value in source.items():
            text = actual[key]
            if value is None: assert text == '', key
            elif isinstance(value, (list, dict)): assert json.loads(text) == value, key
            elif isinstance(value, bool): assert text == str(value), key
            elif isinstance(value, (float, int)): assert float(text) == value, key
            else: assert text == value, key
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--records-output', type=Path)
    parser.add_argument('--replay-records', type=Path)
    parser.add_argument('--expected-version', default='0.10.1')
    args = parser.parse_args()
    report = dict(base_url=args.base_url.rstrip('/'), release=args.expected_version,
                  checked_at_utc=datetime.now(timezone.utc).isoformat(), method=__doc__,
                  timeout_seconds=60, retries=0, checks=[], requests=[])
    captures, endpoint_outputs = [], {}

    def request(path, payload=None, status=200):
        started = perf_counter()
        body = None if payload is None else json.dumps(payload, ensure_ascii=True, allow_nan=False).encode('utf-8')
        entry = dict(path=path, method='GET' if body is None else 'POST', request_sha256=hashlib.sha256(body or b'').hexdigest())
        report['requests'].append(entry)
        try:
            req = Request(report['base_url'] + path, data=body, headers={'Content-Type': 'application/json', 'User-Agent': 'OceanNavigator-P10-Verifier/1'})
            try: response = urlopen(req, timeout=60)
            except HTTPError as error: response = error
            with response: raw, headers, actual_status = response.read(), response.headers, response.status
            entry.update(status=actual_status, bytes=len(raw), seconds=round(perf_counter() - started, 4), response_sha256=hashlib.sha256(raw).hexdigest())
            assert actual_status == status, f'{path}: HTTP {actual_status}, expected {status}; {raw[:200]!r}'
            if path.startswith('/api/'):
                assert headers.get('X-Ocean-App-Version') == args.expected_version, f'{path}: wrong release header'
                assert headers.get('Cache-Control') == 'no-store', f'{path}: wrong API cache policy'
            return raw, headers
        except Exception as error:
            entry.update(seconds=round(perf_counter() - started, 4), error=f'{type(error).__name__}: {str(error)[:400]}')
            raise

    def json_request(path, payload=None, status=200):
        return json.loads(request(path, payload, status)[0])

    def check(name, action):
        started = perf_counter()
        try:
            detail = action()
            item = dict(name=name, passed=True, detail=detail)
        except Exception as error:
            item = dict(name=name, passed=False, error=f'{type(error).__name__}: {str(error)[:700]}')
        item['seconds'] = round(perf_counter() - started, 4)
        report['checks'].append(item)
        print(('PASS ' if item['passed'] else 'FAIL ') + name + ('' if item['passed'] else ': ' + item['error']), flush=True)

    def health():
        body = json_request('/api/health')
        assert body['version'] == args.expected_version and body['status'] == 'ok' and body['case_count'] == 2
        return body
    check('health and expected release', health)

    # Separate local calculations are a consistency reference, not an independent
    # oceanography implementation. Root's original-file tests cover the latter.
    from api.case_store import CaseStore
    from api.expedition_store import ExpeditionStore
    from science.expedition_contracts import PlanQuery, SurveyQuery
    cases = CaseStore(ROOT / 'casepacks')
    local = ExpeditionStore(cases)
    local_references = {}
    for case_id in CASE_IDS:
        manifest, manifest_sha = cases.require(case_id)
        depth_indices = [manifest.coordinates.depth_m.index(depth) for depth in (0, 1000)]
        report.setdefault('source_identities', {})[case_id] = manifest_sha
        for variable in ('temperature', 'salinity'):
            for depth_index in depth_indices:
                for budget, spacing in ((8, 30), (16, 150)):
                    raw_query = {**DEFAULT, 'variable': variable, 'depth_index': depth_index, 'budget': budget, 'min_spacing_km': spacing}
                    q = PlanQuery(**raw_query)
                    for operation in ('plan', 'experiment'):
                        def endpoint(case_id=case_id, q=q, operation=operation):
                            expected = getattr(local, operation)(case_id, q)
                            actual = json_request(f'/api/cases/{case_id}/expedition/{operation}', q.model_dump(mode='json'))
                            equivalent(actual, expected)
                            key = (case_id, operation, q.model_dump_json())
                            local_references[key] = expected
                            endpoint_outputs[key] = actual
                            if operation == 'plan':
                                assert actual['fulfilled'] == (q.budget == 8)
                                assert len(actual['stations']) == 8 if q.budget == 8 else len(actual['stations']) < 16
                                return dict(case_id=case_id, query=q.model_dump(), fulfilled=actual['fulfilled'], stations=len(actual['stations']), candidates=actual['candidate_count'])
                            assert len(actual['runs']) == 24 and len(actual['random_seeds']) == 5
                            if q.budget == 16:
                                assert all(r['status'] == 'failed' and all(r[k] is None for k in ('rmse', 'mae', 'bias')) for r in actual['runs'] if r['strategy'] != 'persistence')
                            assert all(r['budget'] == 0 for r in actual['runs'] if r['strategy'] == 'persistence')
                            return dict(case_id=case_id, query=q.model_dump(), successful_runs=sum(r['status'] == 'ok' for r in actual['runs']), failed_runs=sum(r['status'] == 'failed' for r in actual['runs']), summary=actual['summary'])
                        check(f'{case_id} {variable} {manifest.coordinates.depth_m[depth_index]:g} m budget {budget}: {operation}', endpoint)
                c = manifest.coordinates
                raw_survey = dict(variable=variable, depth_index=depth_index, time_index=5, start=[c.longitude[0], c.latitude[0]], end=[c.longitude[-1], c.latitude[-1]], stations=25)
                def survey(case_id=case_id, raw_survey=raw_survey):
                    q = SurveyQuery(**raw_survey)
                    actual = json_request(f'/api/cases/{case_id}/expedition/survey', raw_survey)
                    expected = local.survey(case_id, q)
                    equivalent(actual, expected)
                    assert actual['simulated'] is True and len(actual['samples']) == 25
                    return dict(case_id=case_id, query=raw_survey, unique_columns=actual['unique_columns'], missing_samples=sum(r['value'] is None for r in actual['samples']), result_sha256=fingerprint(actual))
                check(f'{case_id} {variable} {manifest.coordinates.depth_m[depth_index]:g} m: native simulated survey', survey)

    def compare_module_reference(record):
        recipe = record['replay']['recipe']
        expected_names = ['station_plan'] + (['virtual_survey'] if recipe['survey'] else []) + (['sampling_experiment'] if recipe['experiment'] else [])
        assert [m['module'] for m in record['results']] == expected_names
        assert record['replay']['sources']['methods']['expedition'] == 'p10-sampling-v2'
        for module in record['results']:
            assert module['method_version'] == 'p10-sampling-v2'
            q = SurveyQuery(**recipe['survey']) if module['module'] == 'virtual_survey' else PlanQuery(**recipe['query'])
            operation = {'station_plan': 'plan', 'virtual_survey': 'survey', 'sampling_experiment': 'experiment'}[module['module']]
            equivalent(module['output'], getattr(local, operation)(recipe['case_id'], q))
            assert module['random_seed'] == (recipe['query']['seed'] if module['module'] == 'sampling_experiment' else None)

    def check_zip(record, raw):
        with ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert {'investigation.json', 'settings.json', 'report.html', 'SOURCES.json', 'source-credits.txt', 'README.txt'} <= set(names)
            exported = json.loads(archive.read('investigation.json'))
            validate_bundle(exported, args.expected_version)
            assert exported['results'] == record['results'] and exported['replay'] == record['replay']
            assert json.loads(archive.read('settings.json')) == record['replay']
            assert json.loads(archive.read('SOURCES.json')) == exported['references']
            assert 'HYCOM' in archive.read('source-credits.txt').decode('utf-8')
            html = archive.read('report.html').decode('utf-8')
            assert 'Historical investigation' in html and '<script' not in html.lower()
            rows = {}
            for module in record['results']:
                if module['module'] in CSV_FILES:
                    name, collection = CSV_FILES[module['module']]
                    rows[name] = csv_equal(archive.read(name), module['output'], collection)
            return dict(files=names, numerical_csv_rows=rows, result_sha256=exported['result_sha256'])

    for case_id in CASE_IDS:
        manifest, manifest_sha = cases.require(case_id)
        c = manifest.coordinates
        for variant in ('plan', 'survey', 'experiment', 'impossible'):
            query = {**DEFAULT, 'variable': 'salinity' if variant == 'experiment' else 'temperature', 'depth_index': c.depth_m.index(1000) if variant == 'experiment' else 0}
            if variant == 'impossible': query.update(budget=16, min_spacing_km=150)
            survey = dict(variable=query['variable'], depth_index=query['depth_index'], time_index=3, start=[c.longitude[0], c.latitude[0]], end=[c.longitude[-1], c.latitude[-1]], stations=25) if variant in ('survey', 'experiment') else None
            recipe = dict(mode='expedition', case_id=case_id, query=query, survey=survey, experiment=variant in ('experiment', 'impossible'))
            title = f'P10 verification {case_id} {variant}'
            def capture(recipe=recipe, title=title, manifest_sha=manifest_sha):
                record = json_request('/api/investigations/capture', dict(title=title, recipe=recipe, expected_model_sha256=manifest_sha))
                validate_bundle(record, args.expected_version)
                compare_module_reference(record)
                captures.append(record)
                return dict(title=title, modules=[m['module'] for m in record['results']], result_sha256=record['result_sha256'])
            before = len(captures)
            check(f'capture {case_id} {variant}', capture)
            if len(captures) == before: continue
            saved = captures[-1]
            def replay(saved=saved):
                record = json_request('/api/investigations/replay', saved['replay'])
                validate_bundle(record, args.expected_version)
                assert record['results'] == saved['results'] and record['replay'] == saved['replay']
                return dict(result_sha256=record['result_sha256'])
            check(f'replay {case_id} {variant}', replay)
            check(f'ZIP and exact numerical CSV {case_id} {variant}', lambda saved=saved: check_zip(saved, request('/api/investigations/export', dict(replay=saved['replay'], format='zip'))[0]))
            if case_id == CASE_IDS[0] and variant != 'impossible':
                def direct(saved=saved):
                    html = request('/api/investigations/export', dict(replay=saved['replay'], format='html'))[0].decode('utf-8')
                    assert '<!doctype html>' in html and 'Reconstruction errors do not establish forecast improvement.' in html
                    last = saved['results'][-1]
                    _, collection = CSV_FILES[last['module']]
                    count = csv_equal(request('/api/investigations/export', dict(replay=saved['replay'], format='csv'))[0], last['output'], collection)
                    return dict(primary_module=last['module'], csv_rows=count)
                check(f'direct HTML/CSV export {variant}', direct)

    record_sets = [('original P08', ROOT / 'docs/evidence/p08-local-records.json')]
    if args.replay_records: record_sets.append(('separate P10 process', args.replay_records))
    for label, path in record_sets:
        source_body = path.read_bytes()
        records = json.loads(source_body)
        if isinstance(records, dict): records = records['records']
        report.setdefault('replay_reference_files', []).append(dict(label=label, path=str(path), sha256=hashlib.sha256(source_body).hexdigest(), records=len(records)))
        for index, saved in enumerate(records):
            mode = saved['replay']['recipe']['mode']
            def old_replay(saved=saved):
                record = json_request('/api/investigations/replay', saved['replay'])
                validate_bundle(record, args.expected_version)
                assert record['results'] == saved['results'] and record['replay'] == saved['replay']
                assert record['result_sha256'] == saved['result_sha256']
                return dict(mode=record['replay']['recipe']['mode'], modules=len(record['results']), result_sha256=record['result_sha256'])
            check(f'{label} record {index + 1} {mode}: exact replay', old_replay)
            check(f'{label} record {index + 1} {mode}: evidence archive', lambda saved=saved: check_zip(saved, request('/api/investigations/export', dict(replay=saved['replay'], format='zip'))[0]))

    base = f'/api/cases/{CASE_IDS[0]}/expedition/'
    route = dict(variable='temperature', depth_index=0, time_index=0, start=[86, 13], end=[89, 14], stations=25)
    for name, path, payload, status, code in (
        ('budget too small', base+'plan', {**DEFAULT, 'budget': 2}, 422, 'invalid_request'),
        ('budget too large', base+'plan', {**DEFAULT, 'budget': 17}, 422, 'invalid_request'),
        ('noninteger budget', base+'plan', {**DEFAULT, 'budget': 8.5}, 422, 'invalid_request'),
        ('spacing outside limit', base+'plan', {**DEFAULT, 'min_spacing_km': 151}, 422, 'invalid_request'),
        ('unsupported depth', base+'plan', {**DEFAULT, 'depth_index': 33}, 422, 'invalid_request'),
        ('unsupported variable', base+'plan', {**DEFAULT, 'variable': 'oxygen'}, 422, 'invalid_request'),
        ('unexpected planning time', base+'plan', {**DEFAULT, 'time_index': 6}, 422, 'invalid_request'),
        ('unsupported objective', base+'plan', {**DEFAULT, 'objective': 'forecast_accuracy'}, 422, 'invalid_request'),
        ('unknown case', '/api/cases/not-a-case/expedition/plan', DEFAULT, 404, 'case_not_found'),
        ('outside survey', base+'survey', {**route, 'start': [84, 13]}, 422, 'outside_coverage'),
        ('identical survey endpoints', base+'survey', {**route, 'end': route['start']}, 422, 'invalid_route'),
        ('too many survey stations', base+'survey', {**route, 'stations': 82}, 422, 'invalid_request'),
        ('unsupported survey time', base+'survey', {**route, 'time_index': 7}, 422, 'invalid_request')):
        def guard(path=path, payload=payload, status=status, code=code):
            response = json_request(path, payload, status)
            assert response['error']['code'] == code
            return dict(error_code=code)
        check('reject '+name, guard)
    if captures:
        for kind in ('source', 'method', 'recipe', 'result'):
            def mismatch(kind=kind):
                replay = deepcopy(captures[0]['replay'])
                if kind == 'source': replay['sources']['model_manifest_sha256'] = '0'*64
                elif kind == 'method': replay['sources']['methods']['expedition'] = 'unsupported-expedition-v9'
                elif kind == 'recipe': replay['recipe']['query']['budget'] = 7
                else: replay['expected_result_sha256'] = '0'*64
                if kind in ('source', 'method'): replay['expected_recipe_sha256'] = fingerprint(dict(recipe=replay['recipe'], sources=replay['sources']))
                result = json_request('/api/investigations/replay', replay, 422)
                assert result['error']['code'] == kind+'_mismatch'
                return dict(error_code=result['error']['code'])
            check('reject saved '+kind+' mismatch', mismatch)
        def mismatched_recipe():
            recipe = deepcopy(next(record['replay']['recipe'] for record in captures if record['replay']['recipe']['survey']))
            recipe['survey']['variable'] = 'salinity' if recipe['query']['variable'] == 'temperature' else 'temperature'
            result = json_request('/api/investigations/capture', dict(title='Unsupported mixed-variable recipe', recipe=recipe), 422)
            assert result['error']['code'] == 'invalid_request'
            return dict(error_code='invalid_request')
        check('reject saved plan/survey variable mismatch', mismatched_recipe)

    for path, tokens in (('/', ('Depth Atlas',)), ('/privacy', ('Privacy',)), ('/terms', ('Terms',)),
                         ('/favicon.svg', ('<svg',)), ('/third-party-notices.txt', ('HYCOM', 'Argo', 'Natural Earth')),
                         ('/data-access', ('NetCDF',))):
        def static(path=path, tokens=tokens):
            raw, headers = request(path)
            text = raw.decode('utf-8')
            assert all(token in text for token in tokens)
            return dict(bytes=len(raw), content_type=headers.get('Content-Type'), sha256=hashlib.sha256(raw).hexdigest())
        check('public document '+path, static)

    if args.records_output:
        args.records_output.parent.mkdir(parents=True, exist_ok=True)
        args.records_output.write_text(json.dumps(dict(schema_version='p10-verification-records-v1', base_url=report['base_url'], release=args.expected_version, records=captures), ensure_ascii=True, allow_nan=False) + '\n', encoding='utf-8')
        report['records_written'] = dict(path=str(args.records_output), count=len(captures), sha256=hashlib.sha256(args.records_output.read_bytes()).hexdigest())
    report['passed_checks'] = sum(item['passed'] for item in report['checks'])
    report['failed_checks'] = len(report['checks']) - report['passed_checks']
    report['passed'] = report['failed_checks'] == 0
    report['request_count'] = len(report['requests'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('passed', 'passed_checks', 'failed_checks', 'request_count')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
