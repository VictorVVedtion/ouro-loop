# Example: Blockchain L1

This example shows how Ouro Loop's BOUND system applies to a custom Layer 1 blockchain with PBFT-inspired consensus, UTXO transaction model, and smart contract support. The BOUND definition protects consensus integrity, cryptographic primitives, and state root determinism — areas where incorrect changes cause network forks, funds theft, or chain halts. A real session using this BOUND tested 5 hypotheses and autonomously remediated 4 failures before finding an architectural root cause.

---

## Project Overview

| | |
|---|---|
| **Project** | ExampleChain — High-Performance Layer 1 Blockchain |
| **Language** | Rust (no_std compatible core, async networking via tokio) |
| **Architecture** | PBFT consensus, UTXO model with script-based locking, Merkle Patricia Trie |
| **Session task** | Investigate precommit latency spike from 4ms (idle) to 100-200ms under transaction load |

---

## BOUND Definition

### DANGER ZONES

| Path | Risk |
|------|------|
| `consensus/` | Consensus engine. Incorrect changes = network fork. |
| `crypto/` | Cryptographic primitives. Wrong implementation = funds theft. |
| `state/merkle.rs` | Merkle tree. State root integrity depends on this. |
| `vm/executor.rs` | VM execution. Gas calculation errors = DoS vector. |
| `p2p/protocol.rs` | Network protocol. Breaking changes split the network. |

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

---

## Development Workflow

```bash
# Build
cargo build --release

# Test
cargo test --all
cargo +nightly fuzz run tx_parser -- -max_total_time=60

# Verify Determinism
./scripts/verify_state_root.sh --vectors test_vectors/
```

---

## Session Highlights

The real session using this BOUND produced these results:

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Precommit (under load) | 100-200ms | 4ms | **-98%** |
| Block time (under load) | 111-200ms | 52-57ms | **-53%** |
| TPS Variance | 40.6% | 1.6% | **-96%** |
| SysErr rate | 0.00% | 0.00% | = (IRON LAW) |
| Blocks/sec (soak load) | ~8.0 | ~18.5 | **+131%** |

Key methodology observations:

1. **ROOT_CAUSE gate fired 4 times** — each time it correctly identified symptom-level fixes rather than true root cause resolution.
2. **The 3-failure step-back rule worked** — after 3 consecutive failed hypotheses, the playbook instructed the agent to stop fixing symptoms and re-examine the architecture, leading to the real discovery.
3. **The root cause was architectural, not code-level** — a single-node HTTP bottleneck was causing consensus-wide delays. The fix was a Caddy reverse proxy, not a code change.
4. **The agent caught its own flawed experiment** — when testing an alternative, it ran 4x full stress instead of 1x distributed. It identified the flaw before drawing wrong conclusions.

[:material-file-document: Full Session Log](../session-logs/blockchain-l1.md)

---

## What the BOUND Teaches

This blockchain BOUND demonstrates several patterns:

- **DANGER ZONES cover the irreversible**: consensus logic, cryptography, and state roots are areas where a mistake causes catastrophic, potentially unrecoverable failure.
- **NEVER DO rules prevent subtle disasters**: banning floating point in consensus code and requiring fuzzing for parser changes catches the class of bugs that cause chain forks months after deployment.
- **IRON LAWS are mathematically precise**: determinism, constant-time crypto, and backwards compatibility are binary conditions — they either hold or they do not.
- **BOUND grew after the session**: the LOOP stage added new DANGER ZONES (Caddy load balancer config), new IRON LAWS (distribute stress test load), and new NEVER DO rules (never benchmark against a single node).
