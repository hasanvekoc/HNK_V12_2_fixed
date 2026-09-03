# HNK V7 — hardened testnet/reference node

V7 addresses the V5 audit's software-level findings: runtime SQLite import/startup, signed replay-safe transactions, atomic SQLite commits, intrinsic gas accounting, supply invariant, collision-resistant addresses, persistent blocks/state roots, signed validator votes with 2/3 power quorum, deterministic proposer selection, duplicate-tx protection, block gas limits, API bearer authentication (optional via `HNK_API_TOKEN`), rate limiting, and no wildcard CORS.

Run:
`python -m pytest -q`
`uvicorn server:app --host 127.0.0.1 --port 8787`

This remains a **testnet/reference implementation**, not a declaration of mainnet readiness. Production still requires independently reviewed cryptography/key custody, audited networking, BFT/fork-choice formalization, peer authentication and sync hardening, slashing/economic policy, TLS deployment, fuzz/property/load/soak testing, monitoring, disaster recovery, external security audit, and a public testnet period.
