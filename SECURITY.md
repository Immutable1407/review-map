# Data and security

The app uses one password-gated writer and public review reading. Passwords are salted scrypt hashes, sessions are hashed in SQLite, writes require the same-origin application header, and stale revisions are rejected. HTTPS deployments use `--secure-cookie`.

Runtime data and local configuration are ignored by Git. `scripts/audit_public.py` checks the exact staged files for private paths, runtime files and common credential shapes. The public examples are synthetic.

Report a vulnerability with a minimal reproduction using fictional data; do not include a real token, cookie, source archive or review database in an issue. A report can first be sent through the repository owner's GitHub contact information.
