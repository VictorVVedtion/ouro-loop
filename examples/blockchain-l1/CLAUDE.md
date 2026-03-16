# Project: ExampleChain — High-Performance Layer 1 Blockchain

## Overview

Custom L1 blockchain with PBFT-inspired consensus, UTXO transaction model,
and smart contract support via embedded VM. Written in Rust.

## BOUND

### DANGER ZONES

- `consensus/` — Consensus engine. Incorrect changes = network fork.
- `crypto/` — Cryptographic primitives. Wrong implementation = funds theft.
- `state/merkle.rs` — Merkle tree. State root integrity depends on this.
- `vm/executor.rs` — VM execution. Gas calculation errors = DoS vector.
- `p2p/protocol.rs` — Network protocol. Breaking changes split the network.

### NEVER DO

- Never change the serialization format of blocks or transactions without a version bump
- Never modify consensus threshold constants without formal analysis
- Never use unsafe Rust in crypto modules
- Never skip fuzzing for parser/deserializer changes
- Never merge code that changes state root calculation without 3 independent test vectors
- Never weaken signature verification, even for "performance"
- Never introduce floating point in consensus-critical code

### IRON LAWS

- All consensus-critical code is deterministic — same input always produces same output
- All cryptographic operations use constant-time implementations
- State root is computed identically by all nodes — byte-level determinism
- Gas costs are monotonically non-decreasing with operation complexity
- Block validation is a pure function of (block, parent_state) — no external dependencies
- All network messages are backwards-compatible for at least 2 major versions
- Fuzzing corpus for parsers grows monotonically — never remove test cases

## Architecture

- Rust, no_std compatible core, async networking via tokio
- PBFT consensus with view-change protocol
- UTXO model with script-based locking
- Merkle Patricia Trie for state storage

## Development Workflow

### Build
```bash
cargo build --release
```

### Test
```bash
cargo test --all
cargo +nightly fuzz run tx_parser -- -max_total_time=60
```

### Verify Determinism
```bash
./scripts/verify_state_root.sh --vectors test_vectors/
```
