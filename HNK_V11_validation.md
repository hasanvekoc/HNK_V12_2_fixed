# HNK V11 Hardening Validation
Date: 2026-09-03

## Automated verification
- pytest: 9 passed
- Python compile: PASS
- Docker Compose YAML parse: PASS
- Invalid address/payload validation: PASS
- Validator public-key binding: PASS
- Signature spoof rejection: PASS
- Atomic rollback: PASS
- Genesis/restart persistence: PASS
- Signed quorum + block persistence: PASS
- Real multi-process TCP socket sync: PASS
- Byzantine proposal rejection: PASS
- Node partition/rejoin recovery: PASS

## V11 fixes
- Strict HNK address validation.
- Transfer payload validation during transaction admission, not only execution.
- Validator vote key must match the validator key persisted for that address.
- Peer sync now verifies the remote height and exact committed block hash.
- Duplicate transaction IDs are rejected within the same block as well as across committed blocks.
- Bounded in-memory API rate-limit map cleanup.
- Three-node Compose services use restart policy and health checks.
- Invalid Docker Compose flow-mapping configuration replaced with valid block mappings.

## Release status
V11 is a hardened private-testnet/integration build. Docker containers were not executed in this environment because Docker is unavailable. Mainnet certification still requires independent-host deployment, adversarial consensus testing, secure KMS/HSM key custody, TLS/reverse-proxy hardening, observability/backup/DR, sustained public-testnet soak/load testing, independent security audit, and legal/compliance review.
