#!/usr/bin/env python3
"""Initialize synthetic demo data without replacing an existing collection."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    generated = ROOT / 'data' / 'generated'
    if (generated / 'places-data.js').exists():
        print('Existing collection kept. No demo data was written.')
        return
    generated.mkdir(parents=True, exist_ok=True)
    for name, variable, fixture in [('places-data.js','PLACES_DATA','places.json'),('review-data.js','PLACE_REVIEW_DATA','review-items.json')]:
        payload = json.loads((ROOT/'examples'/fixture).read_text(encoding='utf-8'))
        (generated/name).write_text(f'window.{variable} = '+json.dumps(payload,ensure_ascii=False)+';\n',encoding='utf-8')
    (generated/'review-progress-seed.js').write_text('window.PLACE_REVIEW_SEED = {};\n',encoding='utf-8')
    print('Initialized four fictional places and two calibration exercises.')


if __name__ == '__main__':
    main()
