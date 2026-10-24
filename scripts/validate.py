#!/usr/bin/env python3
"""Validate generated place identity, coordinates, tags and built resources."""
import json
from pathlib import Path
import re
import subprocess
import shutil
from common import load_amap_config

ROOT = Path(__file__).resolve().parents[1]


def assignment(name, variable):
    text = (ROOT/'data/generated'/name).read_text(encoding='utf-8')
    match = re.fullmatch(rf'window\.{variable} = (.*);\s*',text,re.S)
    if not match: raise ValueError(f'Invalid generated assignment: {name}')
    return json.loads(match[1])


def main():
    places = assignment('places-data.js','PLACES_DATA')
    pending = assignment('review-data.js','PLACE_REVIEW_DATA')
    seed = assignment('review-progress-seed.js','PLACE_REVIEW_SEED')
    assert len({p['id'] for p in places})==len(places), 'Duplicate place IDs'
    for place in places:
        lng,lat = place['location']
        assert -180<=lng<=180 and -90<=lat<=90
        assert place['tags'] and place['category']==place['tags'][0]
    key = load_amap_config(ROOT)['webService']['key']
    count = 0
    for name in ('Review-Map.html','Calibration-Desk.html'):
        html = (ROOT/'dist'/name).read_text(encoding='utf-8')
        if key: assert key not in html, 'Server-side AMap key leaked into HTML'
        assert not re.search(r'<script[^>]+src=',html), 'External local script path left in build'
        for script in re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',html,re.S):
            if shutil.which('node'):
                result = subprocess.run(['node','--check'],input=script,text=True,capture_output=True)
                assert result.returncode==0,result.stderr
            count+=1
    print(f'places={len(places)} pending={len(pending)} seed={len(seed)} scripts={count} validation=ok')


if __name__ == '__main__':
    main()
