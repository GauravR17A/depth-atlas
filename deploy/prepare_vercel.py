"""Copy only the compiled public frontend into Vercel's CDN asset directory."""

from pathlib import Path
from shutil import copytree
import hashlib
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
source = root / "web" / "dist"
target = root / "public"
if not (source / "index.html").is_file():
    raise SystemExit("Build the frontend before packaging Vercel assets.")
subprocess.run([sys.executable, '-m', 'science.publication', '--candidate', str(root / 'casepacks'), '--manifest', str(root / 'api/publication.json')], cwd=root, check=True)
copytree(source, target, dirs_exist_ok=True)
for manifest_path in (root / 'casepacks/standards').glob('*.json'):
    exchange = json.loads(manifest_path.read_text())
    if hashlib.sha256((root / 'casepacks/standards' / exchange['file']).read_bytes()).hexdigest() != exchange['sha256']:
        raise SystemExit('Exchange file checksum mismatch: '+exchange['file'])
copytree(root / 'casepacks' / 'standards', target / 'data', dirs_exist_ok=True)
print("Prepared compiled frontend assets for Vercel CDN.")
