"""Same-origin API and optional production frontend. Run from the repository root."""

import logging
import json
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException

from api.contracts import CatalogResponse, ErrorDetail, ErrorResponse, HealthResponse, RegionPreview
from api.case_store import CaseStore, CASE_IDS
from api.guide_store import GuideStore
from api.instrument_store import InstrumentStore
from api.evidence_store import EvidenceStore
from api.feature_store import FeatureStore
from api.support_store import SupportStore
from science.support import SupportRequest
from api.expedition_store import ExpeditionStore
from api.drift_store import DriftStore
from api.heat_store import HeatStore
from api.climate_store import ClimateStore
from api.evolution_store import EvolutionStore
from api.blackout_store import BlackoutStore
from api.wider_store import WiderStore, regional_csv
from science.wider_contracts import WiderQuery, WiderProfileRequest, WiderPack
from science.evolution_contracts import EvolutionQuery
from science.blackout_contracts import BlackoutQuery
from science.climate_contracts import ClimateQuery
from science.heat_contracts import HeatQuery
from science.drift_contracts import DriftQuery
from science.expedition_contracts import PlanQuery, SurveyQuery
from api.investigation_store import InvestigationStore, export_bundle
from science.investigations import CaptureRequest, ReplayRequest, ExportRequest
from science.imported import ImportedComparisonRequest, ImportedCoverageRequest
from api.imported_store import ImportedInstrumentStore, ImportedEvidenceStore
from science.feature_contracts import FeatureQuery, RegionQuery, SectionQuery
from science.evidence_contracts import Comparison, Coverage, MatchSettings
from science.instruments import ImportResult, InstrumentProfile
from starlette.concurrency import run_in_threadpool
from api.version import APP_VERSION
from api.security import ApiGuard, ApiLimits, SECURITY_HEADERS, DOCS_CONTENT_SECURITY_POLICY
from science.contracts import CaseManifest, Observation, OperationResult, UnsupportedData, VariableId

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("ocean.api")

# These are navigation extents, NOT verified data coverage or dataset boundaries.
REGIONS = [
    RegionPreview(
        id="bay-of-bengal", name="Bay of Bengal",
        description="The first planned region for exploring the ocean below the surface.",
        center=(89.0, 14.0), viewport_bounds=(80.0, 5.0, 100.0, 24.0),
    ),
    RegionPreview(
        id="arabian-sea", name="Arabian Sea",
        description="A second Indian Ocean region for linked investigations.",
        center=(64.0, 15.0), viewport_bounds=(50.0, 5.0, 78.0, 26.0),
    ),
    RegionPreview(
        id="tropical-pacific", name="Tropical Pacific",
        description="Selected historical El Niño, La Niña and neutral-event comparisons.",
        center=(-150.0, 0.0), viewport_bounds=(150.0, -20.0, -80.0, 20.0),
    ),
]


def create_app(web_dist: Path | None = None, case_root: Path | None = None, *, security_limits: ApiLimits | None = None) -> FastAPI:
    application = FastAPI(title="Depth Atlas API", version=APP_VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None, swagger_ui_oauth2_redirect_url=None)
    application.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    application.add_middleware(ApiGuard, limits=security_limits, vercel=os.environ.get('VERCEL') == '1')
    publication_directory = Path(os.environ['OCEAN_PUBLICATION_ROOT']).resolve() if case_root is None and os.environ.get('OCEAN_PUBLICATION_ROOT') else None
    publication = None
    if publication_directory:
        from science.publication import selected_root
        case_root, publication = selected_root(publication_directory)
    elif case_root is None and (ROOT / 'api/publication.json').is_file():
        publication = json.loads((ROOT / 'api/publication.json').read_text(encoding='utf-8'))
        if publication.get('app_version') != APP_VERSION:
            raise ValueError('Build the publication manifest for this application version before starting.')
    store = CaseStore(case_root if case_root is not None else ROOT / "casepacks")
    instruments = InstrumentStore((case_root if case_root is not None else ROOT / 'casepacks') / 'instruments')
    evidence = EvidenceStore(store, instruments)
    features = FeatureStore(store, instruments, evidence)
    expeditions = ExpeditionStore(store)
    drifts = DriftStore(store)
    heats = HeatStore(store, instruments)
    climates = ClimateStore(store, instruments)
    evolutions = EvolutionStore(features)
    blackouts = BlackoutStore(evidence)
    wider = WiderStore((case_root if case_root is not None else ROOT / 'casepacks') / 'wider')
    application.state.wider = wider
    investigations = InvestigationStore(store, instruments, evidence, features, expeditions, drifts, heats, climates, evolutions, blackouts)
    guides = GuideStore(store)
    dist = web_dist if web_dist is not None else Path(os.environ.get("OCEAN_WEB_DIST", ROOT / "web" / "dist"))

    def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
        payload = ErrorResponse(error=ErrorDetail(code=code, message=message, request_id=getattr(request.state, "request_id", "unavailable")))
        return JSONResponse(status_code=status, content=payload.model_dump())

    @application.middleware("http")
    async def response_metadata(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Request failed: %s", request.state.request_id)
            response = error_response(request, 500, "internal_error", "The service could not finish this request. Please try again.")
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.rstrip('/') == '/api/docs':
            response.headers['Content-Security-Policy'] = DOCS_CONTENT_SECURITY_POLICY
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers["X-Ocean-App-Version"] = APP_VERSION
        elif request.url.path in ("/", "/index.html", "/startup-recovery.js", "/assets/workspace-fwVeVJXC.js"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/assets/") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        codes = {404: ("not_found", "The requested resource is not available."), 405: ("method_not_allowed", "This request method is not supported.")}
        code, message = codes.get(exc.status_code, ("request_failed", "The request could not be completed."))
        response = error_response(request, exc.status_code, code, message)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError):
        return error_response(request, 422, "invalid_request", "Check the requested values and try again.")

    @application.exception_handler(UnsupportedData)
    async def scientific_error(request: Request, exc: UnsupportedData):
        status = 429 if exc.code == 'regional_capacity' else 404 if exc.code in {"case_not_found", "profile_not_found"} else 413 if exc.code in {"subset_too_large", "file_limits"} else 503 if exc.code == "case_integrity_error" or (exc.code == "source_unavailable" and request.url.path.startswith('/api/wider/')) else 422
        return error_response(request, status, exc.code, str(exc))

    async def wider_body(request: Request, model, limit):
        from pydantic import ValidationError
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise UnsupportedData('invalid_request', 'This request requires JSON.')
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                raise UnsupportedData('file_limits', 'This request exceeds its byte limit.')
            body.extend(chunk)
        try:
            return model.model_validate_json(bytes(body))
        except (ValidationError, ValueError) as exc:
            raise UnsupportedData('invalid_request', 'Check the source, settings, format and request limits.') from exc

    async def wider_query(request: Request):
        return await wider_body(request, WiderQuery, 8192)

    async def wider_profile_query(request: Request):
        return await wider_body(request, WiderProfileRequest, 8192)

    async def wider_pack_body(request: Request):
        return await wider_body(request, WiderPack, 4_500_000)

    async def capture_body(request: Request):
        return await wider_body(request, CaptureRequest, 3_000_000)

    async def replay_body(request: Request):
        return await wider_body(request, ReplayRequest, 3_000_000)

    async def export_body(request: Request):
        return await wider_body(request, ExportRequest, 3_000_000)

    async def imported_comparison_body(request: Request):
        return await wider_body(request, ImportedComparisonRequest, 3_000_000)

    async def imported_coverage_body(request: Request):
        return await wider_body(request, ImportedCoverageRequest, 3_000_000)

    async def support_body(request: Request):
        return await wider_body(request, SupportRequest, 3_000_000)

    @application.post('/api/cases/{case_id}/features/support')
    def structure_support(case_id: str, request: SupportRequest = Depends(support_body)):
        return SupportStore(features).run(case_id, request)

    @application.post('/api/cases/{case_id}/evidence/imported/comparison', response_model=Comparison)
    def imported_comparison(case_id: str, request: ImportedComparisonRequest = Depends(imported_comparison_body)):
        scoped = ImportedEvidenceStore(store, ImportedInstrumentStore(request.import_source, instruments))
        return scoped.comparison(case_id, request.profile_id, request.settings)

    @application.post('/api/cases/{case_id}/evidence/imported/coverage', response_model=Coverage)
    def imported_coverage(case_id: str, request: ImportedCoverageRequest = Depends(imported_coverage_body)):
        scoped = ImportedEvidenceStore(store, ImportedInstrumentStore(request.import_source, instruments))
        return scoped.coverage(case_id, request.settings)

    @application.get('/api/wider/catalog')
    def wider_catalog():
        return wider.catalog()

    @application.post('/api/wider/preview')
    def wider_preview(query: WiderQuery = Depends(wider_query)):
        return wider.preview(query)

    @application.post('/api/wider/subset')
    def wider_subset(query: WiderQuery = Depends(wider_query)):
        return wider.subset(query)

    @application.post('/api/wider/profile')
    def wider_profile(query: WiderProfileRequest = Depends(wider_profile_query)):
        return wider.profile(query)

    @application.post('/api/wider/pack')
    def wider_pack(query: WiderQuery = Depends(wider_query)):
        return wider.pack(query)

    @application.post('/api/wider/replay')
    def wider_replay(pack: WiderPack = Depends(wider_pack_body)):
        return wider.replay(pack)

    @application.post('/api/wider/csv')
    def wider_csv(query: WiderQuery = Depends(wider_query)):
        return Response(regional_csv(wider.pack(query)),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="ocean-region-native.csv"'})

    @application.get('/api/publication')
    def publication_status():
        serving = {k:v for k,v in (publication or {}).items() if k != 'files'}
        # A running worker never switches its data tree during a request.
        status = {'state':'bundled', 'message':'Historical cases are checked and published with an application release. No automatic live-data scheduler is configured.'}
        if publication_directory:
            try:
                journal = json.loads((publication_directory / 'status.json').read_text(encoding='utf-8'))
                pointer = json.loads((publication_directory / 'active.json').read_text(encoding='utf-8'))
                status = {k:journal[k] for k in ('state','started_at','checked_at') if k in journal}
                status['message'] = {'failed':'Last candidate failed validation. Serving publication retained.', 'cancelled':'Last refresh was cancelled. Serving publication retained.', 'validating':'Last recorded stage: validating a candidate. No live job heartbeat is configured. Serving publication retained.', 'staging':'Last recorded stage: staging a candidate. No live job heartbeat is configured. Serving publication retained.'}.get(status.get('state'), 'Prepared publication available.')
                status['restart_required'] = pointer.get('publication_id') != serving.get('publication_id')
            except (OSError, ValueError):
                status = {'state':'status_unavailable','message':'Refresh status is unavailable. This process continues serving its pinned publication.'}
        return {'schema_version':'1','app_version':APP_VERSION,'serving':serving or None,'refresh':status}

    @application.get("/api/health", response_model=HealthResponse)
    def health():
        # Liveness only: this does not claim data readiness or scientific validation.
        entries = store.available()
        return HealthResponse(data_status="historical_case_ready" if entries else "not_configured", case_count=len(entries))

    @application.get('/api/guided-cases')
    def guided_cases():
        return guides.read()

    @application.get("/api/catalog", response_model=CatalogResponse)
    def catalog():
        entries = store.available()
        if not entries:
            return CatalogResponse(regions=REGIONS)
        cases = [manifest.case for manifest, _ in entries]
        regions = [r.model_copy(update={"status": "data_available", "description": "Selected historical GODAS monthly cases and original Argo profiles are available." if r.id=='tropical-pacific' else "A bounded historical HYCOM and Argo case is available."}) if r.id in {c.region_id for c in cases} else r for r in REGIONS]
        from api.expedition_store import SUPPORTED_CASES as expedition_cases
        from science.evolution_contracts import SUPPORTED_CASES as evolution_cases
        unavailable = {}
        for manifest, _ in entries:
            tools = list(manifest.representations.get('unavailable_tools', []))
            if manifest.case.id not in expedition_cases: tools.append('expedition')
            if manifest.case.id not in evolution_cases: tools.append('evolution')
            unavailable[manifest.case.id] = sorted(set(tools))
        return CatalogResponse(regions=regions, data_status="historical_case_ready", message=f"{len(cases)} historical case(s) available. Coverage is limited to their declared bounds and dates, not live conditions.", cases=cases, unavailable_tools=unavailable)

    @application.get("/api/cases/{case_id}", response_model=CaseManifest)
    def case_manifest(case_id: str):
        return store.require(case_id)[0]

    @application.get('/api/instruments')
    def instrument_catalog(case_id: str='bay-bengal-2024-01'):
        store.require(case_id)
        return instruments.catalog(case_id)

    @application.get('/api/products')
    def products():
        from science.products import PRODUCTS
        return {'schema_version': '1', 'products': PRODUCTS.catalog()}

    @application.get('/api/data-access')
    def data_access(case_id: str="bay-bengal-2024-01"):
        store.require(case_id)
        import json
        from adapters.registry import ADAPTERS
        from science.products import ProductMetadata
        record_name='manifest.json' if case_id=='bay-bengal-2024-01' else case_id+'.json'
        record_path = store.root / 'standards' / record_name
        if not record_path.is_file():
            raise UnsupportedData('standards_unavailable', 'This case has native REST access. Its packaged standards download is not available.')
        record = json.loads(record_path.read_text())
        return {'schema_version': '1', 'download': '/data/' + record['file'], 'file': record,
            'rest': '/api/docs', 'standards': {'implementation': 'THREDDS 5.9',
                'protocols': ['WMS 1.3.0', 'WCS 1.0.0', 'OPeNDAP DAP2'] if case_id in {'bay-bengal-2024-01','bay-bengal-2024-03'} else [], 'public_url': None,
                'verified_case_ids': ['bay-bengal-2024-01','bay-bengal-2024-03'],
                'availability': 'Separate local/server package, verified for Bay of Bengal only; no public THREDDS endpoint configured.'},
            'adapters': ADAPTERS.catalog(), 'external_product_contract': ProductMetadata.model_json_schema()}

    @application.get('/data-access', include_in_schema=False)
    @application.get('/data-access/', include_in_schema=False)
    def data_access_page():
        if not (dist / 'data-access.html').is_file(): raise HTTPException(status_code=503)
        return FileResponse(dist / 'data-access.html')

    @application.get('/data/{name}', include_in_schema=False)
    def exchange_download(name: str):
        if name not in {'manifest.json',*[case_id+'.nc' for case_id in CASE_IDS],*[case_id+'.json' for case_id in CASE_IDS if case_id!='bay-bengal-2024-01']}: raise HTTPException(status_code=404)
        if not (store.root/'standards'/name).is_file(): raise HTTPException(status_code=404)
        return FileResponse(store.root / 'standards' / name, media_type='application/x-netcdf' if name.endswith('.nc') else 'application/json')

    def match_settings(variable: Literal['temperature', 'salinity'] = 'temperature', time_index: int = Query(1, ge=0, le=6), time_window_hours: float = Query(6, ge=0, le=72), distance_km: float = Query(5, ge=0, le=50), max_vertical_gap_m: float = Query(500, ge=1, le=1000), qc: Literal['good', 'good_probably_good'] = 'good_probably_good'):
        return MatchSettings(variable=variable, time_index=time_index, time_window_hours=time_window_hours, distance_km=distance_km, max_vertical_gap_m=max_vertical_gap_m, qc=qc)

    @application.get('/api/cases/{case_id}/evidence/coverage', response_model=Coverage)
    def evidence_coverage(case_id: str, settings: MatchSettings = Depends(match_settings)):
        return evidence.coverage(case_id, settings)

    @application.get('/api/cases/{case_id}/evidence/profiles/{profile_id}', response_model=Comparison)
    def evidence_profile(case_id: str, profile_id: str, settings: MatchSettings = Depends(match_settings)):
        return evidence.comparison(case_id, profile_id, settings)

    @application.get('/api/instruments/profiles/{profile_id}', response_model=InstrumentProfile)
    def instrument_profile(profile_id: str):
        return instruments.read(profile_id)

    @application.post('/api/cases/{case_id}/features/search')
    def feature_search(case_id: str, query: FeatureQuery):
        return features.search(case_id,query)

    @application.post('/api/cases/{case_id}/evolution/run')
    def feature_evolution(case_id: str, query: EvolutionQuery):
        return evolutions.run(case_id, query)

    @application.post('/api/cases/{case_id}/blackout/run')
    def observation_blackout(case_id: str, query: BlackoutQuery):
        return blackouts.run(case_id, query)

    @application.get('/api/cases/{case_id}/blackout/catalog')
    def blackout_catalog(case_id: str):
        return blackouts.catalog(case_id)

    @application.post('/api/cases/{case_id}/features/region')
    def feature_region(case_id: str, request: RegionQuery):
        return features.region(case_id,request)

    @application.post('/api/cases/{case_id}/features/section')
    def feature_section(case_id: str, request: SectionQuery):
        return features.section(case_id,request)

    @application.post('/api/cases/{case_id}/expedition/plan')
    def expedition_plan(case_id: str, query: PlanQuery):
        return expeditions.plan(case_id, query)

    @application.post('/api/cases/{case_id}/expedition/survey')
    def expedition_survey(case_id: str, query: SurveyQuery):
        return expeditions.survey(case_id, query)

    @application.post('/api/cases/{case_id}/expedition/experiment')
    def expedition_experiment(case_id: str, query: PlanQuery):
        return expeditions.experiment(case_id, query)

    @application.post('/api/investigations/capture')
    def capture_investigation(request: CaptureRequest = Depends(capture_body)):
        return investigations.capture(request)

    @application.post('/api/investigations/replay')
    def replay_investigation(request: ReplayRequest = Depends(replay_body)):
        return investigations.replay(request)

    @application.post('/api/investigations/export')
    def export_investigation(request: ExportRequest = Depends(export_body)):
        body, media, filename = export_bundle(investigations.replay(request.replay), request.format)
        return Response(body, media_type=media, headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    @application.get('/api/instruments/examples/{name}')
    def instrument_example(name: str):
        return FileResponse(instruments.example(name),filename=name,media_type='application/octet-stream')

    @application.post('/api/instruments/import', response_model=ImportResult)
    async def instrument_import(request: Request, filename: str = Query(min_length=1,max_length=160)):
        # Read a bounded raw body. No disk persistence, URL access or upload history.
        from adapters.instruments import MAX_BYTES, parse_instruments
        if request.headers.get('content-encoding','identity')!='identity':
            raise UnsupportedData('unsupported_format','Compressed request bodies are not supported.')
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>MAX_BYTES: raise UnsupportedData('file_limits','Choose a file no larger than 2 MB.')
        return await run_in_threadpool(parse_instruments,bytes(body),filename)

    @application.post('/api/instruments/inspect')
    async def instrument_inspect(request: Request, filename: str = Query(min_length=1,max_length=160)):
        from adapters.instruments import MAX_BYTES
        from adapters.import_preview import inspect_import
        if request.headers.get('content-encoding','identity')!='identity':
            raise UnsupportedData('unsupported_format','Compressed request bodies are not supported.')
        raw_mapping=request.headers.get('x-ocean-column-mapping')
        mapping=None
        if raw_mapping is not None:
            if len(raw_mapping)>6000: raise UnsupportedData('file_limits','The column mapping is too large.')
            from urllib.parse import unquote
            try: mapping=json.loads(unquote(raw_mapping))
            except (ValueError,TypeError): raise UnsupportedData('invalid_mapping','The column mapping is not valid JSON.')
            if not isinstance(mapping,dict): raise UnsupportedData('invalid_mapping','The column mapping must be an object.')
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>MAX_BYTES: raise UnsupportedData('file_limits','Choose a file no larger than 2 MB.')
        # Recognize a checked public example by bytes, not by the uploader's filename.
        import hashlib
        digest=hashlib.sha256(body).hexdigest()
        source=next((e['source_url'] for e in instruments.catalog()['examples'] if e['sha256']==digest),'')
        return await run_in_threadpool(inspect_import,bytes(body),filename,mapping,source)

    @application.get("/api/cases/{case_id}/profiles/{profile_id}", response_model=Observation)
    def observation(case_id: str, profile_id: str):
        return store.observation(case_id, profile_id)

    @application.get("/api/cases/{case_id}/subset", response_model=OperationResult)
    def subset(case_id: str, variable: VariableId = "temperature", time_index: int = Query(0, ge=0), representation: Literal["analytical", "display"] = "analytical", operation: Literal["depth_slice", "volume"] = "depth_slice", depth_index: int | None = Query(None, ge=0), west: float | None = None, south: float | None = None, east: float | None = None, north: float | None = None):
        return store.subset(case_id, variable, time_index, representation, operation, depth_index, (west,south,east,north))

    @application.get("/", include_in_schema=False)
    def index():
        if not (dist / "index.html").is_file():
            raise HTTPException(status_code=503)
        return FileResponse(dist / "index.html")

    @application.get("/favicon.svg", include_in_schema=False)
    def favicon():
        if not (dist / "favicon.svg").is_file():
            raise HTTPException(status_code=404)
        return FileResponse(dist / "favicon.svg", media_type="image/svg+xml")

    @application.get('/api/cases/{case_id}/heat/catalog')
    def heat_catalog(case_id: str):
        return heats.catalog(case_id)

    @application.get('/api/climate/catalog')
    def climate_catalog():
        return climates.catalog()

    @application.post('/api/climate/analyse')
    def climate_analyse(query: ClimateQuery):
        return climates.analyse(query)

    @application.post('/api/cases/{case_id}/heat/analyse')
    def heat_analyse(case_id: str, query: HeatQuery):
        return heats.analyse(case_id, query)

    @application.get('/api/cases/{case_id}/drift/context')
    def drift_context(case_id: str, depth_index: int = Query(default=0, ge=0, le=32), time_index: int = Query(default=0, ge=0, le=6)):
        return drifts.context(case_id,depth_index,time_index)

    @application.post('/api/cases/{case_id}/drift/run')
    def drift_run(case_id: str, query: DriftQuery):
        return drifts.run(case_id,query)

    @application.post('/api/cases/{case_id}/drift/stream')
    async def drift_stream(case_id: str, query: DriftQuery, request: Request):
        drifts.validate(case_id,query)
        async def events():
            calculation=drifts.stream(case_id,query)
            try:
                while not await request.is_disconnected():
                    event=await run_in_threadpool(lambda:next(calculation,None))
                    if event is None:break
                    yield json.dumps(event,separators=(',',':'),allow_nan=False)+'\n'
            except UnsupportedData as exc:
                yield json.dumps(dict(type='error',code=exc.code,message=str(exc)))+'\n'
            finally:
                calculation.close()
        return StreamingResponse(events(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store, no-transform','Content-Encoding':'identity','X-Accel-Buffering':'no'})

    @application.get("/assets/workspace-fwVeVJXC.js", include_in_schema=False)
    @application.get("/startup-recovery.js", include_in_schema=False)
    def startup_recovery():
        if not (dist / "startup-recovery.js").is_file():
            raise HTTPException(status_code=404)
        return FileResponse(dist / "startup-recovery.js", media_type="text/javascript")

    @application.get("/about", include_in_schema=False)
    @application.get("/about/", include_in_schema=False)
    def about():
        if not (dist / "about.html").is_file():
            raise HTTPException(status_code=503)
        return FileResponse(dist / "about.html")

    @application.get("/privacy", include_in_schema=False)
    @application.get("/privacy/", include_in_schema=False)
    def privacy():
        if not (dist / "privacy.html").is_file():
            raise HTTPException(status_code=503)
        return FileResponse(dist / "privacy.html")

    @application.get("/terms", include_in_schema=False)
    @application.get("/terms/", include_in_schema=False)
    def terms():
        if not (dist / "terms.html").is_file():
            raise HTTPException(status_code=503)
        return FileResponse(dist / "terms.html")

    @application.get("/third-party-notices.txt", include_in_schema=False)
    def notices():
        if not (dist / "third-party-notices.txt").is_file():
            raise HTTPException(status_code=404)
        return FileResponse(dist / "third-party-notices.txt", media_type="text/plain")

    @application.get('/observation-import-guide.txt', include_in_schema=False)
    def import_guide():
        return FileResponse(dist/'observation-import-guide.txt',media_type='text/plain')

    if (dist / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (dist / "licenses").is_dir():
        application.mount("/licenses", StaticFiles(directory=dist / "licenses"), name="licenses")
    return application


app = create_app()
