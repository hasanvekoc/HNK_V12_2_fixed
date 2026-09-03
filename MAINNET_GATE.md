# HNK Mainnet Gate

This package is a hardened **production candidate/reference implementation**, not a claim of independent mainnet certification.

Before real-money mainnet launch, all gates below must be completed and signed off:

1. 3+ independently operated validator organizations/nodes in separate failure domains.
2. Audited P2P transport, authenticated peer discovery, anti-eclipse controls and state/block sync.
3. Formally specified and independently tested BFT fork choice, view/change recovery, equivocation handling, slashing and rewards.
4. Encrypted wallet key custody with production KMS/HSM or equivalent; documented backup/recovery and key rotation.
5. TLS certificates, secrets management, firewalling, least-privilege OS/container deployment and admin MFA/RBAC.
6. Mempool admission, transaction limits, anti-spam economics and distributed rate/connection limits.
7. Fuzz/property, load, soak, crash/restart, byzantine-validator and network-partition tests.
8. Monitoring, alerting, immutable audit logs, backup/restore and disaster-recovery exercises.
9. Public testnet with documented genesis, explorer/RPC and at least 30 days of soak testing.
10. Independent third-party cryptography/blockchain/security audit with all critical/high findings closed.
11. Legal/compliance review for token issuance, KYC/AML, consumer disclosures, privacy and exchange operations in every target jurisdiction.
12. Reproducible mainnet genesis and independent verification from clean machines before activation.
