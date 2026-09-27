"""Reproducible local THREDDS launcher, bound to loopback. No machine-wide install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime/p06'


def install():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for item in json.loads((ROOT/'deploy/standards-runtime-lock.json').read_text()):
        target = RUNTIME / item['name']
        if not target.is_file():
            print('Downloading', item['name'], flush=True)
            with urllib.request.urlopen(item['url'],timeout=120) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
        if hashlib.new(item['algorithm'],target.read_bytes()).hexdigest() != item['digest']:
            raise ValueError(f"Runtime checksum mismatch: {item['name']}")
        if target.suffix == '.zip':
            with zipfile.ZipFile(target) as archive:
                for member in archive.infolist():
                    if not (RUNTIME/member.filename).resolve().is_relative_to(RUNTIME.resolve()):
                        raise ValueError('Archive path leaves runtime directory.')
                archive.extractall(RUNTIME)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true',help='Download and verify pinned Windows Java, Tomcat and TDS binaries.')
    parser.add_argument('--java',type=Path,default=RUNTIME/'jdk-17.0.20.1+1-jre/bin/java.exe')
    parser.add_argument('--tomcat-home',type=Path,default=RUNTIME/'apache-tomcat-10.1.60')
    parser.add_argument('--war',type=Path,default=RUNTIME/'thredds.war')
    parser.add_argument('--base',type=Path,default=RUNTIME/'server')
    parser.add_argument('--port',type=int,default=8096)
    args=parser.parse_args()
    if not 1024 <= args.port <= 65535:parser.error('Choose a nonprivileged TCP port.')
    if args.install: install()
    base=args.base.resolve();home=args.tomcat_home.resolve()
    for name in ['conf','logs','temp','work','webapps','content/thredds','content/data']:
        (base/name).mkdir(parents=True,exist_ok=True)
    for source in (home/'conf').glob('*'):
        if source.is_file(): shutil.copy2(source,base/'conf'/source.name)
    for name in ['catalog.xml','threddsConfig.xml']:
        content=(ROOT/'deploy/standards'/name).read_text().replace('__OCEAN_DATA__',escape((base/'content/data').as_posix(),{'"':'&quot;'}))
        (base/'content/thredds'/name).write_text(content,encoding='utf-8')
    (base/'conf/server.xml').write_text((ROOT/'deploy/standards/server.xml').read_text().replace('port="8096"',f'port="{args.port}"'),encoding='utf8')
    shutil.copy2(args.war,base/'webapps/thredds.war')
    pack=ROOT/'casepacks/standards'
    import xml.etree.ElementTree as ET
    namespace='http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0'
    ET.register_namespace('',namespace)
    catalog_path=base/'content/thredds/catalog.xml'
    catalog=ET.parse(catalog_path);catalog_root=catalog.getroot()
    registered={entry.attrib.get('urlPath') for entry in catalog_root.findall('{'+namespace+'}dataset')}
    for record_path in sorted(pack.glob('*.json')):
        record=json.loads(record_path.read_text())
        source=(pack/record['file']).resolve()
        if source.parent!=pack.resolve() or source.suffix!='.nc':raise ValueError('Invalid exchange filename.')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=record['sha256']: raise ValueError('Exchange file integrity failure.')
        shutil.copy2(source,base/'content/data'/source.name)
        route='ocean/'+source.name
        if route not in registered:
            item=ET.SubElement(catalog_root,'{'+namespace+'}dataset',name=source.stem,ID='ocean/'+source.stem,urlPath=route)
            ET.SubElement(item,'{'+namespace+'}serviceName').text='ocean'
            ET.SubElement(item,'{'+namespace+'}dataType').text='Grid'
    catalog.write(catalog_path,encoding='utf-8',xml_declaration=True)
    command=[str(args.java.resolve()),'-Xms128m','-Xmx768m','-Djava.awt.headless=true',f'-Dcatalina.home={home}',f'-Dcatalina.base={base}',f'-Dtds.content.root.path={base}/content',f'-Djava.io.tmpdir={base}/temp','-cp',os.pathsep.join(str(home/'bin'/p) for p in ['bootstrap.jar','tomcat-juli.jar']),'org.apache.catalina.startup.Bootstrap','start']
    print(f'Serving checked historical cases on http://127.0.0.1:{args.port}/thredds/catalog.html',flush=True)
    raise SystemExit(subprocess.call(command))


if __name__=='__main__': main()
