"""Security boundaries use small deterministic limits, not public load tests."""
import asyncio
import base64
import hashlib
import json
import re
from types import SimpleNamespace
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.responses import Response

from api.app import create_app
from api.security import Admission, ApiGuard, ApiLimits, body_limit, client_identity, CONTENT_SECURITY_POLICY, DOCS_CONTENT_SECURITY_POLICY

ROOT = Path(__file__).resolve().parents[1]


def test_body_is_bounded_before_json_parser_without_content_length():
    seen = []
    async def endpoint(scope, receive, send):
        seen.append(True)
        await Response('unexpected')(scope, receive, send)
    async def run():
        events = iter([{'type':'http.request','body':b'x'*40_000,'more_body':True},
                       {'type':'http.request','body':b'x'*40_000,'more_body':False}])
        output = []
        async def receive(): return next(events)
        async def send(event): output.append(event)
        await ApiGuard(endpoint)({'type':'http','path':'/api/cases/test/drift/run','method':'POST','headers':[], 'client':('client',1)}, receive, send)
        assert output[0]['status'] == 413
    asyncio.run(run())
    assert not seen


def test_upload_timeout_releases_slots():
    async def endpoint(scope, receive, send): await Response('ok')(scope, receive, send)
    async def run():
        guard = ApiGuard(endpoint, replace(ApiLimits(), body_timeout_seconds=.02, concurrent_requests=1, concurrent_calculations=1))
        output=[]
        async def slow(): await asyncio.sleep(1)
        async def send(event): output.append(event)
        scope={'type':'http','path':'/api/instruments/import','method':'POST','headers':[], 'client':('client',1)}
        await guard(scope, slow, send)
        assert output[0]['status'] == 408
        output.clear()
        async def fast(): return {'type':'http.request','body':b'','more_body':False}
        await guard(scope, fast, send)
        assert output[0]['status'] == 200
    asyncio.run(run())


def test_body_deadline_is_absolute_even_when_chunks_are_immediately_available(monkeypatch):
    clock=[1.]
    monkeypatch.setattr('api.security.time', SimpleNamespace(monotonic=lambda: clock[0]))
    async def run():
        output=[]
        received=[]
        async def endpoint(scope,receive,send): raise AssertionError('Expired upload must not run')
        guard=ApiGuard(endpoint,replace(ApiLimits(),body_timeout_seconds=15))
        async def receive():
            received.append(True)
            clock[0]=20.
            return {'type':'http.request','body':b'x','more_body':True}
        async def send(event): output.append(event)
        await guard({'type':'http','path':'/api/test','method':'POST','headers':[], 'client':('client',1)},receive,send)
        assert output[0]['status']==408
        assert len(received)==1
    asyncio.run(run())


def test_concurrency_rejects_without_queue_and_recovers():
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        async def endpoint(scope, receive, send):
            started.set()
            await finish.wait()
            await Response('ok')(scope, receive, send)
        guard = ApiGuard(endpoint, replace(ApiLimits(), concurrent_calculations=1))
        scope={'type':'http','path':'/api/test','method':'POST','headers':[], 'client':('client',1)}
        async def receive(): return {'type':'http.request','body':b'','more_body':False}
        first, second=[], []
        async def send_first(event): first.append(event)
        async def send_second(event): second.append(event)
        task=asyncio.create_task(guard(scope, receive, send_first))
        await started.wait()
        await guard(scope, receive, send_second)
        assert second[0]['status'] == 429
        assert b'service_busy' in second[1]['body']
        finish.set()
        await task
        second.clear()
        await guard(scope, receive, send_second)
        assert second[0]['status'] == 200
    asyncio.run(run())


def test_default_budget_accepts_three_parallel_sessions_and_read_burst():
    async def run():
        entered=[]
        finish=asyncio.Event()
        async def endpoint(scope, receive, send):
            entered.append(scope['path'])
            if scope['method']=='POST': await finish.wait()
            await Response('ok')(scope,receive,send)
        guard=ApiGuard(endpoint)
        outputs=[[] for _ in range(3)]
        async def receive(): return {'type':'http.request','body':b'{}','more_body':False}
        async def call(index,method):
            async def send(event): outputs[index].append(event)
            await guard({'type':'http','path':'/api/test','method':method,'headers':[], 'client':('shared-network',index)},receive,send)
        tasks=[asyncio.create_task(call(i,'POST')) for i in range(3)]
        while len(entered)<3: await asyncio.sleep(0)
        finish.set()
        await asyncio.gather(*tasks)
        assert all(output[0]['status']==200 for output in outputs)
        for i in range(120):
            outputs[0].clear()
            await call(0,'GET')
            assert outputs[0][0]['status']==200
    asyncio.run(run())


def test_disconnect_and_endpoint_exception_release_admission():
    async def run():
        async def endpoint(scope,receive,send): raise ValueError('controlled test')
        guard=ApiGuard(endpoint,replace(ApiLimits(),concurrent_requests=1,concurrent_calculations=1))
        scope={'type':'http','path':'/api/test','method':'POST','headers':[], 'client':('client',1)}
        async def disconnect(): return {'type':'http.disconnect'}
        async def receive(): return {'type':'http.request','body':b'{}','more_body':False}
        async def send(event): raise AssertionError('No response should start')
        await guard(scope,disconnect,send)
        for _ in range(2):
            try: await guard(scope,receive,send)
            except ValueError: pass
            else: raise AssertionError('Exception must propagate to the safe error middleware')
    asyncio.run(run())


def test_limit_refill_and_bounded_identity_table():
    clock=[10.]
    guard=Admission(replace(ApiLimits(), request_burst=2, requests_per_minute=60, clients=2), lambda:clock[0])
    assert [guard.take('one',False) for _ in range(3)] == [0,0,1]
    clock[0]+=1
    assert guard.take('one',False)==0
    assert guard.take('two',False)==0
    assert guard.take('three',False)==10
    assert len(guard._entries)==2
    assert all(isinstance(key,bytes) and len(key)==32 for key in guard._entries)
    clock[0]+=601
    assert guard.take('three',False)==0
    assert len(guard._entries)==1


def test_only_deployment_verified_proxy_header_is_trusted():
    scope={'client':('203.0.113.1',123)}
    headers={'x-forwarded-for':'198.51.100.1','x-real-ip':'198.51.100.2','x-vercel-forwarded-for':'198.51.100.3'}
    assert client_identity(scope,headers,False)=='203.0.113.1'
    assert client_identity(scope,headers,True)=='198.51.100.3'
    headers['x-vercel-forwarded-for']='198.51.100.3, 203.0.113.4'
    assert client_identity(scope,headers,True)=='203.0.113.1'


def test_endpoint_budget_preserves_existing_supported_imports():
    assert body_limit('/api/instruments/import')==2_000_000
    assert body_limit('/api/instruments/inspect')==2_000_000
    assert body_limit('/api/investigations/replay')==3_000_000
    assert body_limit('/api/cases/test/evidence/imported/comparison')==3_000_000
    assert body_limit('/api/cases/test/features/support')==3_000_000
    assert body_limit('/api/wider/replay')==4_500_000
    assert body_limit('/api/cases/test/features/search')==65_536


def test_rate_limit_response_has_retry_and_standard_metadata(tmp_path):
    app=create_app(tmp_path,security_limits=replace(ApiLimits(), request_burst=2, requests_per_minute=1))
    with TestClient(app) as client:
        assert client.get('/api/health').status_code==200
        assert client.get('/api/health').status_code==200
        r=client.get('/api/health',headers={'x-forwarded-for':'203.0.113.200'})
        assert r.status_code==429
        assert int(r.headers['retry-after'])>0
        assert r.headers['cache-control']=='no-store'
        assert r.headers['x-request-id']==r.json()['error']['request_id']
        assert r.headers['x-ocean-app-version']
        assert client.get('/privacy').status_code != 429


def test_cross_site_post_denied_but_same_origin_and_cli_allowed(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        for headers in ({'origin':'https://other.example'}, {'origin':'null'}, {'origin':'https://[bad'}, {'sec-fetch-site':'cross-site'}):
            assert client.post('/api/instruments/import?filename=test.csv',content=b'a',headers=headers).status_code==403
        for headers in ({'origin':'http://testserver','sec-fetch-site':'same-origin'}, {}):
            assert client.post('/api/instruments/import?filename=test.csv',content=b'a',headers=headers).status_code==422


def test_length_encoding_and_url_rejections(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        path='/api/cases/test/drift/run'
        assert client.post(path,content=b'{}',headers={'content-length':'65537'}).status_code==413
        assert client.post(path,content=b'{}',headers={'content-length':'-1'}).status_code==400
        assert client.post(path,content=b'{}',headers={'content-length':'9'*5000}).status_code==400
        assert client.post(path,content=b'{}',headers={'content-encoding':'gzip'}).status_code==422
        assert client.get('/api/health?x='+'a'*8192).status_code==431


def test_headers_and_exact_inline_scripts(tmp_path):
    (tmp_path/'index.html').write_text('ok')
    with TestClient(create_app(tmp_path)) as client:
        r=client.get('/')
        assert r.headers['x-frame-options']=='DENY'
        assert "frame-ancestors 'none'" in r.headers['content-security-policy']
        assert 'geolocation=()' in r.headers['permissions-policy']
        docs=client.get('/api/docs')
        assert docs.headers['content-security-policy']==DOCS_CONTENT_SECURITY_POLICY
        for html,policy in [(ROOT.joinpath('web/index.html').read_text(encoding='utf-8'),CONTENT_SECURITY_POLICY),(docs.text,DOCS_CONTENT_SECURITY_POLICY)]:
            for script in re.findall(r'<script>(.*?)</script>',html,re.S):
                digest=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
                assert "'sha256-"+digest+"'" in policy
        js_policy=CONTENT_SECURITY_POLICY.split('script-src ')[1].split(';')[0]
        assert 'unsafe-inline' not in js_policy and 'unsafe-eval' not in js_policy
    config=json.loads(ROOT.joinpath('vercel.json').read_text())
    csp=next(h['headers'][0]['value'] for h in config['headers'] if h['source']=='/((?!api/docs).*)')
    assert csp==CONTENT_SECURITY_POLICY
