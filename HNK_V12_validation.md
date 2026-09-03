# HNK V12 Hardened Validation
Date: 2026-09-03

## Automated verification
- pytest: **14 passed**
- Python compileall: **PASS**
- V8 regression suite: **PASS**
- V11 hardening suite: **PASS**
- V12 hardening suite: **PASS**
- malformed vote handling: PASS
- invalid transaction signature normalization: PASS
- unsupported contract-kind rejection: PASS
- genesis/block integrity tamper detection: PASS
- strict address validation: PASS
- chain continuity validation: PASS

## V12 changes
- Defensive base64 decoding with bounded input.
- Cryptographic signature failures normalized to safe validation errors.
- SQLite busy timeout added for multi-process contention.
- Startup blockchain integrity verification added.
- Strict rejection of unsupported contract transaction kinds rather than silently charging fees.
- Block input/vote count validation strengthened.
- API balance endpoint validates HNK address format.
- Mempool maximum enforced.
- Peer sync validates chain ID and previous-block hash.
- Peer proposal now exposes chain ID and previous hash explicitly.

## Environment limitation
Docker is not installed in this execution environment, so an actual Docker daemon/container run cannot be claimed here. The application and Compose files are syntax-checked where possible, while the multi-process TCP test remains the executable network validation.

## Release status
**NOT MAINNET CERTIFIED.** Remaining independent gates include real Docker/independent-host deployment, adversarial Byzantine/fork-choice testing, production key custody, TLS/reverse proxy, monitoring/DR, long-duration public testnet soak, economic review, independent third-party audit, and legal/compliance review.
