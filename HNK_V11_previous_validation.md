# HNK V10 Real Socket Network Validation
Date: 2026-09-02

## Result
**6/6 PASS** on a real multi-process TCP/HTTP socket network using three independently running HNK node processes.

### Passed
1. Three independent nodes started and exposed network APIs.
2. Signed transaction committed on node 1 and propagated by peer sync.
3. All three nodes converged to the same height and block hash.
4. All three nodes converged to the same recipient balance/state.
5. Byzantine/mutated proposal with stale votes was rejected.
6. Node 3 was taken offline, node 1 advanced, node 3 restarted and recovered the missing block/state through peer synchronization.

## Additional checks
- `python -m py_compile core.py server.py`: PASS
- Peer authentication required for peer status/proposal endpoints.
- Peer sync validates the complete transaction body through normal `commit_block` verification before persistence.
- Three-node Docker Compose configuration included.

## Important limitation
Docker daemon is unavailable in this execution environment, so the exact Docker containers were not executed here. The socket test was executed with three separate OS processes on localhost, which validates real TCP socket transport and multi-process synchronization but is not equivalent to an independent-host deployment.

## Mainnet status
**NO-GO / NOT CERTIFIED MAINNET.** Remaining production gates include independent-host networking, adversarial Byzantine/equivocation/fork-choice testing, secure validator key custody (KMS/HSM), TLS/reverse proxy deployment, monitoring/backup/DR, sustained public-testnet soak/load testing, economic/security review, independent third-party audit, and legal/compliance review.
