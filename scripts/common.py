"""Small configuration helpers; no browser-side map key is needed."""
import json
import os


def load_amap_config(root):
    path = root / 'config' / 'amap-config.local.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    key = os.environ.get('AMAP_WEB_SERVICE_KEY') or data.get('webService', {}).get('key', '')
    return {'webService': {'key': key}}
