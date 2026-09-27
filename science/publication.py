"""Maintainer-only, bounded publication of a prepared case-pack tree.

No public mutation endpoint, arbitrary URL fetch, scheduler or in-place dataset
replacement. Readers pin a release at startup. Historical source dates persist.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from api.case_store import CaseStore
from api.instrument_store import InstrumentStore
from api.version import APP_VERSION

MAX_BYTES = 250_000_000
MAX_STORE_BYTES = 1_000_000_000


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with path.open('rb') as stream:
        value = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
        return value.hexdigest()


def atomic(path, value):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, separators=(',', ':'), ensure_ascii=True)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def inventory(root: Path, check=lambda: None):
    """Inventory exact prepared bytes, reject links and validate declared cases."""
    root = root.resolve(); files = []; total = 0
    # Path ordering differs between Windows (case-folded) and POSIX. Identity
    # must use one explicit ordering of portable relative path strings.
    for path in sorted(root.rglob('*'), key=lambda p: p.relative_to(root).as_posix()):
        check()
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Publication trees cannot contain links or escaping paths.')
        if not path.is_file(): continue
        size = path.stat().st_size; total += size
        if total > MAX_BYTES or size > 100_000_000 or len(files) >= 5000:
            raise ValueError('Prepared publication exceeds the file or byte budget.')
        files.append(dict(path=path.relative_to(root).as_posix(), bytes=size, sha256=digest(path)))
    known = {f['path']: f for f in files}
    cases = []; store = CaseStore(root)
    for manifest, sha in store.available():
        check()
        for declared in manifest.files:
            entry = known.get(manifest.case.id + '/' + declared['path'])
            if not entry or entry['sha256'] != declared['sha256'] or ('bytes' in declared and entry['bytes'] != declared['bytes']):
                raise ValueError('Prepared case checksum mismatch: ' + manifest.case.id)
        # Checks decoded dimensions and source samples without changing values.
        for i in range(manifest.case.time_count):
            for variable in manifest.case.variables:
                check(); store._read_array(manifest.case.id, 'analytical', variable, i)
                store._read_array(manifest.case.id, 'display', variable, i)
        cases.append(dict(id=manifest.case.id, title=manifest.case.title, time_start=manifest.case.time_start,
                          time_end=manifest.case.time_end, manifest_sha256=sha,
                          sources=[dict(title=s.title, retrieved_at=s.retrieved_at, source_url=s.source_url,
                                        licence=s.licence, citation=s.citation) for s in manifest.sources]))
    if not cases: raise ValueError('No compatible registered model cases were found.')
    instruments = InstrumentStore(root / 'instruments')
    for case in cases:
        for p in instruments.index(case['id'])['profiles']:
            check(); instruments.read(p['id'])
    for example in instruments.catalog().get('examples', []):
        check(); instruments.example(example['name'])
    for path in (root / 'standards').glob('*.json'):
        record = json.loads(path.read_text(encoding='utf-8')); entry = known.get('standards/' + record['file'])
        if not entry or entry['sha256'] != record['sha256']: raise ValueError('Standards checksum mismatch.')
    identity = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(schema_version='1', app_version=APP_VERSION, publication_id=identity, checked_at=now(),
                bytes=total, files=files, cases=cases)


def publish(candidate: Path, destination: Path, timeout=120, cancel=lambda: False, progress=lambda message: None):
    candidate = candidate.resolve(); destination = destination.resolve()
    if candidate == destination or destination.is_relative_to(candidate) or candidate.is_relative_to(destination):
        raise ValueError('Candidate and publication store must be separate directories.')
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / 'refresh.lock'
    # Exclusive lock is never removed by a competing attempt.
    with lock.open('x', encoding='utf-8') as stream: stream.write(str(os.getpid()))
    attempt = uuid4().hex; stage = destination / 'releases' / attempt
    started = now(); deadline = time.monotonic() + timeout; activated = False
    def check():
        if cancel(): raise InterruptedError('Refresh cancelled. Previous publication retained.')
        if time.monotonic() > deadline: raise TimeoutError('Refresh timed out. Previous publication retained.')
    def status(state, message):
        atomic(destination / 'status.json', dict(attempt=attempt, started_at=started, checked_at=now(), state=state, message=message))
        progress(state + ': ' + message)
    try:
        status('validating', 'Checking the prepared candidate. Previous publication remains active.')
        info = inventory(candidate, check)
        used = sum(p.stat().st_size for p in destination.rglob('*') if p.is_file())
        if used + info['bytes'] > MAX_STORE_BYTES:
            raise ValueError('Publication store exceeds 1 GB. Archive an unused release before retrying.')
        status('staging', 'Copying checked files to an isolated release.')
        pack = stage / 'casepacks'; pack.mkdir(parents=True)
        for item in info['files']:
            check(); source = candidate / item['path']; target = pack / item['path']; target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink() or not source.resolve().is_relative_to(candidate): raise ValueError('Candidate changed during staging.')
            with source.open('rb') as read, target.open('xb') as write:
                remaining = item['bytes']
                while True:
                    check(); chunk = read.read(min(1024*1024, remaining+1))
                    if not chunk: break
                    remaining -= len(chunk)
                    if remaining < 0: raise ValueError('Candidate changed during staging.')
                    write.write(chunk)
            if remaining or digest(target) != item['sha256']: raise ValueError('Candidate changed during staging.')
        check(); atomic(stage / 'publication.json', info)
        status('ready', 'Validated release ready for atomic activation.')
        check(); atomic(destination / 'active.json', dict(release=attempt, publication_id=info['publication_id'], app_version=APP_VERSION))
        activated = True
        status('published', 'Publication selected. Restart the service to use it; running readers keep their pinned release.')
        return info
    except BaseException as error:
        if not activated:
            status('cancelled' if isinstance(error, (InterruptedError, KeyboardInterrupt)) else 'failed', str(error)[:300])
            if stage.exists() and stage.resolve().is_relative_to((destination / 'releases').resolve()): shutil.rmtree(stage)
        raise
    finally:
        lock.unlink(missing_ok=True)


def selected_root(destination: Path):
    pointer = json.loads((destination / 'active.json').read_text(encoding='utf-8'))
    if not re.fullmatch(r'[a-f0-9]{32}', pointer.get('release', '')) or pointer.get('app_version') != APP_VERSION:
        raise ValueError('Publication and application versions are incompatible.')
    release = destination / 'releases' / pointer['release']
    expected = json.loads((release / 'publication.json').read_text(encoding='utf-8'))
    actual = inventory(release / 'casepacks')
    if expected.get('app_version') != APP_VERSION or actual['publication_id'] != pointer.get('publication_id') or actual['publication_id'] != expected.get('publication_id'):
        raise ValueError('Selected publication failed integrity verification.')
    return release / 'casepacks', expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--store', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if bool(args.store) == bool(args.manifest): parser.error('Choose either --store or --manifest.')
    info = publish(args.candidate, args.store, args.timeout, progress=lambda line: print(line, flush=True)) if args.store else inventory(args.candidate)
    if args.manifest: atomic(args.manifest, info)
    print(json.dumps({k:info[k] for k in ('publication_id','app_version','checked_at','bytes')}))


if __name__ == '__main__': main()
