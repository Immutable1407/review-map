#!/usr/bin/env python3
"""Register immutable capture versions and stage evidence-backed place batches."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'美食','甜品','咖啡','酒吧','公园','展馆','小店','游玩'}
CAPTURE_STATES = {'success','partial','failed','unsupported','needs_auth'}
CONTENT_STATES = {'complete','partial','metadata_only','media_complete_text_partial','stub'}
TEXT_SOURCES = {'platform_original','platform_auto','platform_description','user_provided','jina_reader','local_ocr','authorized_asr','none'}


def canonical(url):
    if not url: return ''
    p = urlsplit(url)
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password:
        raise ValueError('Source URLs must be HTTP(S) without credentials')
    return urlunsplit((p.scheme,p.netloc,p.path,'',''))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def append(path, row):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(row,ensure_ascii=False)+'\n')


def write_new(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def process(payload, root=ROOT, deliver=False, date=None):
    os.umask(0o077)
    if payload.get('schemaVersion') != 1:
        raise ValueError('Expected intake schemaVersion 1')
    sources = payload.get('sources',[])
    by_id = {}
    for source in sources:
        key = source.get('source_id')
        if not isinstance(key,str) or not key.strip() or key in by_id: raise ValueError('Provide unique stable source_id values')
        if source.get('capture_status') not in CAPTURE_STATES or source.get('content_state') not in CONTENT_STATES or source.get('text_source') not in TEXT_SOURCES:
            raise ValueError('Invalid source status or text_source')
        if not isinstance(source.get('text',''),str): raise ValueError('Source text must be a string')
        canonical(source.get('canonical_url',''))
        by_id[key] = source
    confirmed, pending = [], []
    for original in payload.get('places',[]):
        place = dict(original)
        name = place.get('name','').strip()
        if not name or any(c in name for c in '\r\n：:'):
            raise ValueError('Each place needs a single-line name without a delimiter')
        ids = place.get('sourceIds') or []
        if not ids or any(key not in by_id for key in ids): raise ValueError('Every place must reference a registered input source')
        food = place.get('recommendedFood',[])
        if not isinstance(food,list) or any(not isinstance(f,str) or '\n' in f or '\r' in f for f in food): raise ValueError('recommendedFood must contain single-line strings')
        category = place.get('category','')
        evidence = place.get('evidence',[])
        valid_quotes = all(e.get('source_id') in ids and isinstance(e.get('quote'),str) and e['quote'].strip() and e['quote'] in by_id[e['source_id']].get('text','') for e in evidence)
        usable = all(by_id[key]['capture_status'] in {'success','partial'} and by_id[key]['content_state'] != 'stub' for key in ids)
        reason = None
        if place.get('confirmation') != 'confirmed': reason = 'place_name_needs_confirmation'
        elif category not in CATEGORIES: reason = 'category_needs_confirmation'
        elif not usable or not evidence or not valid_quotes: reason = 'source_evidence_missing_or_unverified'
        place.update(name=name,city=str(place.get('city') or '').strip(),category=category,sourceIds=list(dict.fromkeys(ids)))
        if reason: pending.append({**place,'review_reason':reason})
        else: confirmed.append(place)
    # A plain handoff name must identify one city; ambiguous names stay in review.
    cities = {}
    for p in confirmed: cities.setdefault(p['name'],set()).add(p['city'])
    ambiguous = {name for name,values in cities.items() if len(values)>1}
    pending += [{**p,'review_reason':'same_name_in_multiple_cities'} for p in confirmed if p['name'] in ambiguous]
    merged = {}
    for p in confirmed:
        if p['name'] in ambiguous: continue
        key = (p['name'],p['city'])
        if key not in merged: merged[key] = dict(p)
        else:
            target = merged[key]
            target['recommendedFood'] = list(dict.fromkeys(target.get('recommendedFood',[])+p.get('recommendedFood',[])))
            target['sourceIds'] = list(dict.fromkeys(target['sourceIds']+p['sourceIds']))
    date = date or datetime.now().astimezone().strftime('%Y-%m-%d')
    if not re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}',date): raise ValueError('Date must be YYYY-M-D')
    datetime.strptime(date,'%Y-%m-%d')
    state = root/'data/acquisition'
    run = state/'compiled'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3))
    run.mkdir(parents=True,exist_ok=False)
    ingest = read_rows(state/'ingest-ledger.jsonl')
    retrievals = read_rows(state/'retrieval-ledger.jsonl')
    for key,source in by_id.items():
        encoded = json.dumps(source,ensure_ascii=False,sort_keys=True).encode()
        checksum = hashlib.sha256(encoded).hexdigest()
        previous = [r for r in retrievals if r['source_id']==key]
        if previous and previous[-1]['sha256']==checksum: continue
        version = len(previous)+1
        slug = hashlib.sha256(key.encode()).hexdigest()[:20]
        target = state/'raw'/slug/f'{version}.json'
        write_new(target,source)
        event = {'source_id':key,'source_version':version,'sha256':checksum,'raw_path':str(target.relative_to(root)),'run':str(run.relative_to(root))}
        if not any(row['source_id']==key for row in ingest):
            append(state/'ingest-ledger.jsonl',{'source_id':key,'first_raw_path':event['raw_path']})
        append(state/'retrieval-ledger.jsonl',event)
    delivered = {key for event in read_rows(state/'handoff-ledger.jsonl') for key in event['item_keys']}
    items = []
    for p in merged.values():
        item_key = hashlib.sha256(json.dumps(p,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if item_key not in delivered: items.append((item_key,p))
    write_new(run/'review.json',pending)
    lines,metadata = [],{}
    for _,p in items:
        lines.append(p['name']+('：'+'，'.join(p.get('recommendedFood',[])) if p.get('recommendedFood') else ''))
        metadata[p['name']] = {'city':p['city'],'category':p['category'],'sourceIds':p['sourceIds'],'sourceUrls':[canonical(by_id[key].get('canonical_url','')) for key in p['sourceIds'] if by_id[key].get('canonical_url')]}
    if lines:
        (run/'places.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        write_new(run/'metadata.json',metadata)
    result = {'schemaVersion':1,'run':str(run.relative_to(root)),'sources':len(sources),'staged_places':len(items),'needs_review':len(pending),'discovery_performed':False,'delivered_file':None}
    if deliver and items:
        raw = root/'raw'; raw.mkdir(parents=True,exist_ok=True)
        counter = 1
        while True:
            name = date+'_update'+(f'-{counter}' if counter>1 else '')+'.md'
            target = raw/name
            try:
                with target.open('x',encoding='utf-8') as file: file.write('\n'.join(lines)+'\n')
                break
            except FileExistsError: counter += 1
        path = root/'config/raw-update-metadata.local.json'; path.parent.mkdir(parents=True,exist_ok=True)
        settings = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        settings[name] = metadata
        temporary = path.with_name(path.name+'.tmp-'+secrets.token_hex(3))
        write_new(temporary,settings); os.replace(temporary,path)
        result['delivered_file'] = str(target.relative_to(root))
        append(state/'handoff-ledger.jsonl',{'run':result['run'],'file':result['delivered_file'],'item_keys':[key for key,_ in items]})
    write_new(run/'handoff.json',result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--deliver',action='store_true',help='After validation, copy a new place batch into raw/ and annotate it')
    parser.add_argument('--date',help='YYYY-M-D handoff date')
    args = parser.parse_args()
    try:
        print(json.dumps(process(json.loads(args.input.read_text(encoding='utf-8')),deliver=args.deliver,date=args.date),ensure_ascii=False,indent=2))
    except (ValueError,KeyError) as error: parser.error(str(error))


if __name__ == '__main__':
    main()
