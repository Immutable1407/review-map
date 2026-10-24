#!/usr/bin/env python3
"""Set the review login password interactively; never place secrets in CLI arguments."""
import argparse
import getpass
import secrets
from pathlib import Path

from serve import ROOT, connect, password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'personal' / 'reviews.sqlite3')
    parser.add_argument('--replace', action='store_true', help='explicitly replace an existing password and revoke sessions')
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with connect(args.db) as conn:
        exists = conn.execute('SELECT 1 FROM owner').fetchone()
        if exists and not args.replace:
            raise SystemExit('Password already configured. Use --replace only when intentionally resetting it.')
        password = getpass.getpass('Password (not echoed): ')
        if not 8 <= len(password) <= 256:
            raise SystemExit('Password must contain 8–256 characters.')
        salt = secrets.token_hex(16)
        conn.execute('INSERT OR REPLACE INTO owner VALUES (1,?,?)', (salt, password_hash(password, salt)))
        conn.execute('DELETE FROM sessions')
    print('Login password configured; existing sessions revoked.')


if __name__ == '__main__':
    main()
