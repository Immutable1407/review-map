#!/usr/bin/env python3
"""Inspect the exact Git index before publication; report paths, never values."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = ('raw/','data/','dist/','third_party/','.private-')
PATTERNS = {
    'home-directory path': re.compile(r'/(?:Users|home)/[^\s/"\']+/'),
    'GitHub credential': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'cloud credential': re.compile(r'AKIA[0-9A-Z]{16}'),
}
LITERALS = re.compile(r'''(?i)["']?(?:password|api[_-]?key|securityJsCode|access_token|client_secret)["']?\s*[:=]\s*["']([^"'\r\n]+)["']''')
TEST_VALUES = {'test-owner-password','test-passphrase-123','utf-8','current-password'}


def inspect(name, data):
    problems=[]
    if name.startswith(BLOCKED) or name.endswith(('.local.json','.sqlite3','.sqlite3-wal','.db','.pem','.key')):
        problems.append('runtime/private file')
    if name.endswith(('.woff2','.png','.jpg','.webp')): return problems
    try: text=data.decode('utf-8')
    except UnicodeDecodeError: return problems+['unexpected binary file']
    for label,pattern in PATTERNS.items():
        if pattern.search(text): problems.append(label)
    if any(len(value)>=8 and value not in TEST_VALUES and not value.startswith(('YOUR_','EXAMPLE_','example-')) for value in LITERALS.findall(text)):
        problems.append('literal credential')
    return problems


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree',action='store_true',help='Read tracked working files instead of index blobs')
    args=parser.parse_args()
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    findings=[]
    for name in filter(None,names):
        data=(ROOT/name).read_bytes() if args.worktree else subprocess.check_output(['git','show',':'+name],cwd=ROOT)
        for issue in inspect(name,data): findings.append((name,issue))
    for name,issue in findings: print(f'{name}: {issue}')
    if findings: raise SystemExit(1)
    print(f'Public index audit passed: {len(list(filter(None,names)))} tracked files')


if __name__=='__main__': main()
