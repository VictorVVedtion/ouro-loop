# Phase Plan: Optimize CommitWait Latency (CW: 80ms -> 40ms)

## Meta

- **Complexity**: Complex
- **Total Phases**: 3
- **BOUND Interaction**: Adjacent to DANGER ZONE (`consensus/`), touches Network Phase.
- **Estimated Effort**: 1 day

## Task Summary

Current CommitWait (CW) is statically sized at 80ms, providing safety margins but artificially capping Soak TPS. We need to implement an adaptive CW that drops to 40ms (and dynamically scales to 10ms under high load) without causing excessive round escalations or breaking the determinism IRON LAW.

## Core Metric

Soak TPS improves >30%, while `SysErr` remains at 0.00% under a 30-minute stress test.

---

## Phase 1: Adaptive CommitWait Implementation — HIGH

**Entry criteria:**
- [x] All existing consensus determinism tests pass.
- [x] Network latency simulation environment active.

**Scope:**
- `consensus/timing.rs` — implement adaptive scaling logic based on mempool depth.
- `tests/test_timing.rs` — new unit tests for scaling bounds.

**Exit criteria:**
- [x] CW correctly bounds between 10ms and 80ms based on local load.
- [x] IRON LAW: Block validation function remains pure (timing is externalized).

---

## Phase 2: GossipSub Precommit Profiling — CRITICAL

**Entry criteria:**
- [x] Phase 1 verified via unit tests.

**Scope:**
- `p2p/gossip.rs` — profile and handle message degradation.
- *Remediation Risk:* High load might cause precommit phase bursts.

**Exit criteria:**
- [x] Liveness monitor accurately catches GossipSub message drops.
- [x] Precommit bursts do not trigger hard consensus failures, only round escalations.
- [x] `SysErr` metric holds at 0.00%.

---

## Phase 3: Soak Test Verification — CRITICAL

**Entry criteria:**
- [x] Phase 2 verifiable under simulated load (short burst tests passed).

**Scope:**
- Execute 30-minute full soak stress test (`SOAK_DURATION=30m`).

**Exit criteria:**
- [x] Validator nodes do not fall out of sync permanently (catch-up logic triggers correctly).
- [x] Soak Avg TPS demonstrates >30% improvement over 80ms baseline.

---

## Autonomous Discovery & Remediation Log

| Phase | Discovery / Trigger | Action Taken (Autonomous) | Verification |
|-------|---------------------|---------------------------|--------------|
| 2 | VERIFY Failed: Precommit phase spiked to 108-211ms under load, causing validator-0 to fall behind (gap=323 blocks). | Consulted `remediation.md`. Detected issue was not in DANGER ZONE (was P2P networking lag, not state root calculation). Autonomously updated Liveness Monitor catch-up logic to tolerate transient GossipSub degradation. | Restarted test. Validator caught up successfully, round escalation rate stabilized at ~7.9%. IRON LAWS maintained. |
| 3 | VERIFY Failed: Test exited after ~208 seconds. | Root Cause Gate: Identified `SOAK_DURATION` env variable was dropped by shell before binary start. Autonomously fixed bash script. | Re-ran command. Stress test ran successfully for full 30m. |
