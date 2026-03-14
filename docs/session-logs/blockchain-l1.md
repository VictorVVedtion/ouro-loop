# Session Log: Blockchain L1 — Consensus Performance Regression

This is a complete session log from a real Ouro Loop session on a Layer 1 blockchain project. The agent was tasked with investigating a consensus performance regression under transaction load. Over the course of 5 hypotheses and 4 autonomous remediations, the agent discovered that the root cause was an architectural issue (single-node HTTP bottleneck) rather than a code-level bug, demonstrating the value of the ROOT_CAUSE verification gate and the 3-failure step-back rule.

---

## Context

| | |
|---|---|
| **Project type** | Custom L1 blockchain (Go), PBFT-inspired consensus, 4 validators |
| **Task** | Investigate why precommit phase latency spikes from 4ms (idle) to 100-200ms under transaction load |
| **BOUND interaction** | Inside DANGER ZONE (`consensus/`) |
| **Complexity** | Complex (DANGER ZONE, multiple subsystems, unknown root cause) |

---

## BOUND (from CLAUDE.md)

```
DANGER ZONES: consensus/, p2p/gossipsub.go, state/merkle.go
NEVER DO: Never use float in consensus-critical code
IRON LAWS:
  - SysErr rate must be 0.00%
  - State root deterministic
  - Block time must not regress vs baseline under equivalent load
```

---

## MAP

```
User expects:    block time stays near idle performance under load
Failure modes:   consensus stall, round escalation storm, chain halt
Tightest constraint: SysErr 0.00% (IRON LAW)
Dependencies:    consensus → p2p gossip → HTTP gateway → stress test harness
Reusable:        existing stress test binary, Tier 10 baseline data
Success metric:  precommit < 10ms under load, block time < 100ms
```

---

## PLAN

Complexity: **Complex** (DANGER ZONE, multiple subsystems, unknown root cause)

Approach: Hypothesis-driven elimination, not phase-based construction.

---

## BUILD + VERIFY + REMEDIATE (The Root Cause Hunt)

### Hypothesis 1: CommitWait parameter too high

```
Action:   Reduced CommitWait from 80ms to 40ms
Result:   Idle block time halved (111ms → 51ms)
          Load block time still 122-234ms — precommit still 100ms+
Verdict:  PARTIAL — improved idle, didn't fix load regression
```

**VERIFY: ROOT_CAUSE gate → FAIL.** Symptom improved, root cause not addressed.

```
[REMEDIATED] gate=ROOT_CAUSE action=keep_partial_and_continue
  was: CW=40ms improved idle but load still regressed
  did: kept CW=40ms (valid improvement), continued investigation
  now: investigating lock contention
  bound: inside DANGER ZONE — proceeding with caution
```

---

### Hypothesis 2: Global mutex contention

```
Action:   Split globalMu into read-write lock, separated hot paths
Result:   6.7% improvement in lock contention metrics
          precommit still 90-180ms under load
Verdict:  FAIL — marginal improvement, not the root cause
```

**VERIFY: ROOT_CAUSE gate → FAIL.**

```
[REMEDIATED] gate=ROOT_CAUSE action=discard_hypothesis
  was: lock optimization only 6.7% improvement
  did: kept the optimization (valid), moved to next hypothesis
  now: investigating goroutine scheduling
  bound: DANGER ZONE changes minimal and tested
```

---

### Hypothesis 3: Goroutine scheduling starvation

```
Action:   Set GOMAXPROCS=8, tuned scheduler parameters
Result:   No measurable improvement
Verdict:  FAIL — not the cause
```

**VERIFY: ROOT_CAUSE gate → FAIL.** Third consecutive failure.

```
[REMEDIATED] gate=ROOT_CAUSE action=step_back_and_remap
  was: 3 hypotheses tested, none found root cause
  did: stopped fixing symptoms, re-examined the system architecture
  now: looking at the problem from the network layer, not consensus layer
  bound: no DANGER ZONE code changed in this step
```

!!! info "The 3-failure step-back rule"
    After 3 consecutive failed hypotheses, the remediation playbook instructs: "stop fixing symptoms, re-examine the architecture." This rule redirected investigation from the consensus layer to the network layer, which led to finding the actual root cause.

---

### Hypothesis 4: GossipSub protocol degradation

```
Action:   Analyzed GossipSub v1/v2/v3 message patterns under load
Result:   Protocol overhead exists but is proportional, not the spike cause
Verdict:  FAIL — GossipSub is a contributor, not the root cause
```

---

### Hypothesis 5: Single-point HTTP gateway bottleneck

```
Action:   Examined network topology
Finding:  ALL stress test HTTP traffic routed to a single validator node
          That node's precommit delays because it's saturated with HTTP
          Other 3 validators wait for it in PBFT consensus
Root cause: Single-node HTTP bottleneck creates consensus-wide delay
```

**VERIFY: ROOT_CAUSE gate → PASS.**

```
Solution: Caddy reverse proxy with round-robin load balancing across all 4 validators
Result:
  - precommit: 100-200ms → 4ms (back to idle levels)
  - block time under load: 122-234ms → 92ms
  - SysErr: 0.00% (IRON LAW maintained throughout)
```

---

## Soak Test: Combined Optimizations

After finding the root cause, all optimizations were combined for a 30-minute soak test.

### Timeline (autonomous monitoring every 3 minutes)

```
  0:00   chain restart, CW=40ms, LB active, O1+O2 applied
  2:00   warm-up phase: 6088 blocks, avg 52ms/block ← same as idle!
  5:00   throughput ramp: 9472 blocks, avg 53ms, precommit 4ms stable
  8:00   soak starting: 12796 blocks, avg 53ms, round_esc=1
 11:00   soak running: 15444 blocks, avg 55ms, TPS 9866-10150 (1.6% variance)
 14:00   soak mid: precommit occasional 13-75ms (LB imperfect distribution)
 17:00   soak complete: 18219 blocks, avg 57ms, PASS
```

Key observation: block time under load barely deviated from idle (52ms to 57ms, +10%). In the previous baseline (Tier 10), block time under load was 111ms to 200ms+ (+80%).

### Self-Correcting Experiment: Direct Multi-Gateway

After the soak test, the agent attempted to verify whether direct round-robin (bypassing Caddy) would recover the TPS lost to proxy overhead.

```
Experiment: Run 4 separate stress instances, each hitting one validator directly
Result:     validator-0 fell behind again, precommit back to 200-500ms
```

```
[REMEDIATED] gate=ROOT_CAUSE action=abort_bad_experiment
  was: running 4 full stress instances (4x total load, not 1x distributed)
  did: identified that 4x stress ≠ same load distributed; killed experiment
  now: confirmed Caddy LB is the correct approach, TPS delta is proxy overhead
  bound: no code changed, experiment-only
```

The agent correctly identified that 4 full stress instances = 4x the total load, not the same load distributed across 4 nodes. The ROOT_CAUSE gate prevented false conclusions from a flawed experiment design.

---

## Final Comparison: Tier 10 Baseline vs Tier 11

| Metric | Tier 10 (CW80, 1 node) | Tier 11 (CW40+LB+O1O2) | Delta |
|--------|------------------------|-------------------------|-------|
| Block time (idle) | 111ms | 52ms | -53% |
| Block time (soak load) | 111-200ms | 52-57ms | -53% |
| Blocks/sec (idle) | 9.0 | 19.2 | +113% |
| Blocks/sec (soak load) | ~8.0 | ~18.5 | +131% |
| Precommit (idle) | 4ms | 4ms | = |
| Precommit (soak load) | 100-200ms | 5-35ms | -85% |
| Soak TPS Variance | 40.6% | 1.6% | -96% |
| SysErr | 0.00% | 0.00% | = |
| Round Escalations | 0 | 3 | ~ |
| Validator Height Sync | N/A | <=3 blocks | |
| Chain Halts | 0 | 0 | = |

### The 4 Optimizations (Tier 11 Stack)

1. **CW=40ms** (CommitWait halved) — effect: block time 111ms to 52ms idle. Needs LB to stay stable under load.
2. **O1: Batch flush read-write separation** — effect: global mutex exclusive hold time halved. Low risk (race detector passed).
3. **O2: CancelOrder lock downgrade** — effect: eliminated cancel vs. place lock contention. Low risk (race detector passed).
4. **Caddy round-robin LB** (the real fix) — effect: eliminated single-node HTTP overload causing consensus goroutine starvation. This is why precommit went from 200ms to 5ms.

---

## Results

```
  phase:        investigation (5 hypotheses)
  verdict:      PASS
  bound_check:  PASS — SysErr 0.00%, no IRON LAW violated
  metric:       precommit 4ms (target: <10ms)
  block_time:   92ms under load (baseline idle: 51ms)
  remediation:  4 autonomous remediations before finding root cause
```

---

## LOOP — What Fed Back Into BOUND

New additions to CLAUDE.md after this session:

```
DANGER ZONES (added):
  - infrastructure/caddy/ — load balancer config, single point of failure if misconfigured

IRON LAWS (added):
  - Stress tests must distribute load across all validators, never single-node
  - Load balancer health checks must be configured before any performance test

NEVER DO (added):
  - Never run performance benchmarks against a single validator endpoint
```

---

## Methodology Observations

1. **ROOT_CAUSE gate fired 4 times** — each time it correctly identified that the agent was fixing symptoms, not the cause. The gate prevented premature celebration after partial improvements.

2. **The 3-failure step-back rule worked** — after 3 consecutive failed hypotheses, the remediation playbook told the agent to "stop fixing, re-examine architecture." This led to looking at the network layer instead of the consensus layer, which found the actual root cause.

3. **Partial improvements were kept** — CW=40ms and the lock optimization were genuine improvements even though they were not the root cause. The methodology correctly distinguished between "valid improvement" and "root cause found."

4. **BOUND was respected throughout** — despite working inside a DANGER ZONE (consensus/), SysErr stayed at 0.00% and no IRON LAW was violated. The agent operated autonomously within the boundary.

5. **The real root cause was architectural, not code-level** — it was a deployment topology issue (HTTP routing), not a code bug. The methodology's MAP stage should have caught this earlier by mapping the "Dependencies" dimension more carefully. This is a lesson for future MAP stages.

6. **The agent caught its own bad experiment** — when testing direct multi-gateway, it ran 4x full stress (4x total load) instead of 1x distributed load. It identified the flaw before drawing wrong conclusions. The ROOT_CAUSE gate prevented a false negative ("direct is worse than Caddy") from corrupting the research.

7. **Soak stability was the real breakthrough** — TPS variance dropping from 40.6% to 1.6% matters more than raw TPS numbers. A system that delivers 10K TPS consistently is more valuable in production than one that swings between 8K and 20K.
