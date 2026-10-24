#!/usr/bin/env python3
"""Invoke separately installed yichen-content-archive executors, not a scraper."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://github.com/mcncarl/yichen-skills'
CONTRACT_REF = '6e0c0ae43b5fd168040b8eb5193392e47b6f6301'


def route(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Use one HTTPS content URL without embedded credentials')
    host = (parsed.hostname or '').lower()
    if host in {'douyin.com','www.douyin.com','v.douyin.com'}:
        if host != 'v.douyin.com' and not parsed.path.startswith('/video/'):
            raise ValueError('Use an exact Douyin video URL, not an account or search page')
        return 'douyin', 'douyin_download.py'
    if host in {'xiaohongshu.com','www.xiaohongshu.com','xhslink.com'}:
        if host != 'xhslink.com' and not parsed.path.startswith(('/explore/','/discovery/item/')):
            raise ValueError('Use an exact Xiaohongshu note URL')
        return 'xiaohongshu', 'xiaohongshu_fetch.py'
    raise ValueError('This bridge supports exact Douyin videos and Xiaohongshu notes; use normalized local captures for other sources')


def invocation(skill, url, output, download=False, python=sys.executable):
    platform, script = route(url)
    target = output/'video.mp4' if platform == 'douyin' else output/'note'
    args = [python, str(skill/'scripts'/script), url, str(target)]
    if not download:
        args.append('--metadata-only' if platform == 'douyin' else '--skip-media')
    return platform, script, args


def acquire(skill, url, root=ROOT, download=False, python=sys.executable):
    os.umask(0o077)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3)
    output = root/'data/acquisition/runs'/stamp
    platform, script, args = invocation(skill, url, output, download, python)
    if not (skill/'SKILL.md').is_file() or not (skill/'scripts'/script).is_file():
        raise ValueError('Point --upstream-skill at an existing yichen-content-archive directory')
    output.mkdir(parents=True, exist_ok=False)
    (output/'input.url').write_text(url+'\n',encoding='utf-8')
    environment = {k:v for k,v in os.environ.items() if 'COOKIE' not in k.upper()}
    timed_out = False
    with (output/'executor.log').open('wb') as log:
        try:
            result = subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,env=environment,timeout=300)
            code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out, code = True, -1
    parsed = urlsplit(url)
    canonical = urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
    source_id = platform + ':url:' + hashlib.sha256(canonical.encode()).hexdigest()[:16]
    for file in output.rglob('*.metadata.json'):
        try:
            metadata = json.loads(file.read_text(encoding='utf-8'))
            stable = metadata.get('aweme_id') or metadata.get('note_id')
            if stable: source_id = platform + ':' + str(stable)
        except (ValueError,OSError):
            pass
    status = 'success' if code == 0 else 'failed'
    media = any(file.suffix.lower() in {'.mp4','.mp3','.m4a','.wav'} for file in output.rglob('*'))
    manifest = {
        'schemaVersion':1,'producer':'review-map acquisition bridge',
        'source_id':source_id,'platform':platform,'canonical_url':canonical,
        'source_url_ref':'input.url','capture_status':status,
        'content_state':'media_complete_text_partial' if media else 'metadata_only',
        'text_source':'none','discovery_performed':False,
        'backend':f'yichen-content-archive/{script}',
        'upstream_repository':UPSTREAM,'interface_reference':CONTRACT_REF,
        'requested_media_download':download,'exit_code':code,
        'artifacts':[str(p.relative_to(output)) for p in sorted(output.rglob('*')) if p.is_file()],
        'fetched_at':datetime.now(timezone.utc).isoformat(),
        'failure':'executor_timeout' if timed_out else ('executor_failed' if code else None)
    }
    (output/'capture.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return output,manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--upstream-skill',type=Path,required=True)
    parser.add_argument('--python',default=sys.executable,help='Python environment with upstream dependencies')
    parser.add_argument('--download-media',action='store_true',help='Explicitly include media downloads; default is metadata/text only')
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    try:
        if args.dry_run:
            platform,script,command = invocation(args.upstream_skill,args.url,Path('<new-run>'),args.download_media,args.python)
            print(json.dumps({'platform':platform,'backend':'yichen-content-archive/'+script,'media_download':args.download_media,'mode_flags':command[4:]},ensure_ascii=False))
            return
        output,manifest = acquire(args.upstream_skill,args.url,download=args.download_media,python=args.python)
        print(json.dumps({'run':str(output.relative_to(ROOT)),'capture_status':manifest['capture_status'],'content_state':manifest['content_state'],'backend':manifest['backend']}))
        if manifest['capture_status'] != 'success': raise SystemExit(1)
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
