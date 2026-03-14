# Frequently Asked Questions

Comprehensive answers to common questions about Ouro Loop, bounded autonomy, and autonomous AI coding. Each answer is designed to be independently useful as a standalone explanation.

---

## General

### What is Ouro Loop?

**Ouro Loop** is an open-source framework that gives AI coding agents (Claude Code, Cursor, Aider, Codex) a structured autonomous loop with runtime-enforced guardrails. It implements bounded autonomy — the developer defines absolute constraints (DANGER ZONES, NEVER DO rules, IRON LAWS) using the BOUND system, then the agent loops autonomously through Build → Verify → Self-Fix cycles. When verification fails, the agent doesn't ask for help — it consults its remediation playbook, reverts, tries a different approach, and reports what it did.

### How is this different from just using .cursorrules or CLAUDE.md?

`.cursorrules` and `CLAUDE.md` define static instructions that the agent can ignore. Ouro Loop adds a **runtime loop** — state tracking, multi-layer verification, autonomous remediation, and phase management. The agent doesn't just follow rules; it verifies compliance, detects drift, and self-corrects. Most importantly, BOUND constraints are enforced by runtime hooks (exit 2 hard-block), not by the agent's good behavior.

| Feature | Static Rules | Ouro Loop |
|---------|-------------|-----------|
| Constraint definition | Yes | Yes |
| Runtime enforcement | No | Yes (hooks, exit 2) |
| Verification gates | No | Yes (5 gates) |
| Autonomous remediation | No | Yes |
| State tracking | No | Yes |
| Loop feedback | No | Yes |

### When should I use Ouro Loop?

Use Ouro Loop when you need an AI agent to work autonomously for extended periods without human babysitting:

- **Overnight autonomous development** — Define BOUND, start the agent, sleep
- **Long-running refactoring** — Phase-based refactoring with verification gates
- **Production-safe AI coding** — Financial systems, blockchain, medical software
- **Multi-phase feature development** — Complex features decomposed into severity-ordered phases
- **CI/CD with AI agents** — Autonomous build failure resolution

### When should I NOT use Ouro Loop?

Don't use Ouro Loop for:

- **Quick prototypes or hackathon projects** — BOUND setup overhead (~30 min) isn't worth it
- **Single-file scripts** — The methodology overhead exceeds the benefit
- **Real-time interactive coding** — Ouro Loop is designed for "set it and let it run"
- **Learning/exploration** — Human-in-the-loop is more appropriate when you want to observe

---

## Bounded Autonomy

### What is bounded autonomy in AI coding?

Bounded autonomy is a paradigm where AI coding agents are granted full autonomous decision-making power within explicitly defined constraints. By defining the 20 things an agent cannot do (the BOUND), you implicitly authorize it to do the 10,000 things required to solve the problem. It's the middle path between human-in-the-loop (constant interruptions) and unbounded agents (unconstrained risk).

### How do I define good boundaries?

Good boundaries share three properties:

1. **Specific** — "Never use float for monetary values" is better than "be careful with money"
2. **Measurable** — IRON LAWS should be verifiable programmatically (coverage thresholds, error rates)
3. **Born from real incidents** — The best NEVER DO rules encode lessons from actual failures

Start with three questions:

- Which files would cause catastrophic failure if incorrectly modified? → DANGER ZONES
- What coding practices are absolutely prohibited? → NEVER DO
- What measurable conditions must always be true? → IRON LAWS

### Does BOUND grow over time?

Yes. The LOOP stage (Stage 5) feeds lessons learned back into BOUND. After each autonomous session, new DANGER ZONES, NEVER DO rules, and IRON LAWS are added based on what was discovered. In a real blockchain session, three new rules were added after the agent discovered that performance benchmarks must distribute load across validators.

---

## Autonomous Remediation

### Can the agent really fix its own mistakes?

Yes, within BOUND. When verification fails and the issue is inside the boundary (not a DANGER ZONE), the agent consults `modules/remediation.md` for a decision playbook: revert, retry with a different approach, or escalate. It reports what it did, not what it's thinking of doing.

In a real blockchain session, the agent autonomously remediated 4 failures across 5 hypotheses and found a root cause that was architectural (HTTP routing), not code-level — without human intervention.

### What happens when the agent gets stuck in a loop?

The ROOT_CAUSE verification gate detects stuck loops by monitoring whether the agent is fixing symptoms or causes. The `root-cause-tracker.sh` hook tracks per-file edit frequency:

- 3+ edits to the same file → warning
- 5+ edits → strong warning

After 3 consecutive remediation failures, the step-back rule activates: "stop fixing symptoms, re-examine the architecture." This breaks the loop by forcing the agent to look at the problem from a different angle.

### What if the agent needs to touch a DANGER ZONE?

The `bound-guard.sh` hook blocks DANGER ZONE edits with exit code 2 (hard-block). The agent cannot proceed. It receives a denial reason explaining which DANGER ZONE was triggered. The agent must either:

1. Find an alternative approach that doesn't touch the DANGER ZONE
2. Escalate to the human for explicit approval

This is by design — DANGER ZONES represent files where autonomous changes could cause catastrophic failure.

---

## Verification Gates

### What are the five verification gates?

| Gate | Checks | Prevents |
|------|--------|----------|
| **EXIST** | Do referenced files, APIs, modules actually exist? | Hallucination |
| **RELEVANCE** | Is current work related to the original task? | Scope drift |
| **ROOT_CAUSE** | Is this fixing the cause, not a symptom? | Stuck loops |
| **RECALL** | Can the agent still recall key constraints? | Context decay |
| **MOMENTUM** | Is meaningful progress being made? | Velocity death |

### How to prevent AI agents from hallucinating file paths?

Ouro Loop's EXIST verification gate checks whether referenced files, APIs, and modules actually exist before the agent proceeds. The `bound-guard.sh` hook also validates file paths against the project structure. If a file doesn't exist, the gate fails and triggers autonomous remediation — the agent corrects its reference instead of proceeding with hallucinated paths.

### How to prevent context decay in long AI coding sessions?

Ouro Loop addresses context decay through the RECALL verification gate and the `recall-gate.sh` hook. The gate monitors whether the agent can still recall key constraints. The hook fires before context compression (PreCompact event) and re-injects the BOUND section into the compressed context, preventing constraint amnesia during long sessions.

---

## Setup & Requirements

### Do I need to install anything?

No. Zero dependencies. Pure Python 3.10+ standard library. Clone the repo and point your agent at `program.md`. Optionally install hooks for runtime enforcement.

### How long can the agent run autonomously?

As long as phases remain. Each phase is independently verifiable, so the agent can run for hours across many phases. The NEVER STOP instruction in `program.md` keeps the loop going until all phases pass or an EMERGENCY-level issue is hit.

### Which AI agents work with Ouro Loop?

Ouro Loop is agent-agnostic. It works with any AI coding assistant that can read files and execute terminal commands:

- **Claude Code** — Native support with 4 runtime enforcement hooks
- **Cursor** — Via `.cursorrules` referencing Ouro Loop modules
- **Aider** — Terminal-based, reads `program.md` as instructions
- **Codex CLI** — OpenAI's agent, follows methodology via prompting
- **Windsurf** — Codeium's IDE, instruction-based integration

### How do I add guardrails to Claude Code?

Ouro Loop provides 4 Claude Code Hooks that enforce constraints at the tool level:

```bash
# Install hooks
cp ~/.ouro-loop/hooks/settings.json.template .claude/settings.json
# Edit paths in settings.json to point to your installation
```

The `bound-guard.sh` hook parses your CLAUDE.md DANGER ZONES and physically blocks edits to protected files. No agent can bypass exit code 2. See the [Claude Code Integration Guide](guides/claude-code.md) for details.

---

## Philosophy

### What is the Ouroboros Contract?

The Ouroboros Contract is the philosophical foundation of Ouro Loop, expressed in [The Manifesto](manifesto.md). The core idea: by explicitly defining the inescapable boundary of what the agent *cannot* do (the Event Horizon), you paradoxically grant it absolute freedom to execute everything else. The serpent bites its own tail — consuming its own errors so the creator may rest.

### How is Ouro Loop related to autoresearch?

Ouro Loop is directly inspired by Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) — an autonomous ML experiment loop where the AI modifies `train.py`, trains for 5 minutes, checks val_bpb, and keeps or reverts. Ouro Loop extends this paradigm from ML to general software engineering, adding multi-layer verification, formal constraint definitions (BOUND), and runtime enforcement hooks.

### Why "Ouro Loop"?

"Ouro" comes from "Ouroboros" — the ancient symbol of a serpent eating its own tail. It represents the self-consuming, self-correcting nature of the framework: the agent builds, verifies, fails, consumes its own failure, and tries again. The loop is continuous and self-sustaining.
