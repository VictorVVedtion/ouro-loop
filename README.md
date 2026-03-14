# Ouro Loop

*A constraint-driven development methodology for autonomous AI agents.*

![teaser](progress.png)

*One day, frontier AI research used to be done by meat computers in between eating, sleeping, having other fun, and synchronizing once in a while using sound wave interconnect in the ritual of "group meeting". That era is long gone... This repo is the story of how it all began. -@karpathy, March 2026, [autoresearch](https://github.com/karpathy/autoresearch).*

The original `autoresearch` repo gave an AI agent a tiny LLM training setup and let it experiment autonomously overnight. It succeeded because it provided a rigid constraint space (a 5-minute training budget, a single `val_bpb` metric) within which the AI was free to mutate architecture and hyperparameters.

**Ouro Loop maps this exact paradigm to general software engineering.**

We give an AI agent a development methodology—boundaries, verification layers, and remediation playbooks—and let it guard your codebase autonomously. 

The core idea: **You don't start from "what to build" — you start from "what must never break."**

## How it works

The repo provides the methodology modules and a lightweight runtime (`framework.py`) that the AI agent uses to track its state.

- **`framework.py`** — The runtime. It tracks the current phase, runs multi-layer verifications, checks bounds, and logs results.
- **`modules/`** — The methodology. Six core stages (`bound.md`, `map.md`, `plan.md`, `build.md`, `verify.md`, `loop.md`) and the critical `remediation.md` playbook. **These provide the context to the AI agent.**
- **`CLAUDE.md`** — The project-specific boundaries (DANGER ZONES, NEVER DO, IRON LAWS). **This is edited and iterated on by the human.**

By design, Ouro Loop shifts the AI from a passive monitor ("Human, something broke, what do I do?") to a bounded ouro ("I tried this, it broke an iron law, so I autonomously reverted and am now trying this alternative approach").

## Quick start

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Install dependencies (if you haven't)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Enter your target software project directory
cd /path/to/your/project

# 3. Initialize Ouro Loop in that project
python /path/to/ouro-loop/prepare.py init .

# 4. Generate the CLAUDE.md template to define your boundaries
python /path/to/ouro-loop/prepare.py template claude .
```

Write your `CLAUDE.md` to define your project's `DANGER ZONES` and `IRON LAWS`. Then, spin up your AI agent (Claude, Cursor, Aider, OpenAlpha) in your repository and point it at the `CLAUDE.md` and the Ouro Loop modules.

## The Paradigm Shift: Precision Autonomy

Read the [Manifesto](MANIFESTO.md) for the full deep-dive.

The current generation of AI agents operate like brilliant but reckless junior developers. They optimize for the shortest path to a passing test. In real engineering—consensus engines, financial systems, medical software—this "vibecoding" is dangerous.

Ouro Loop replaces unstructured "vibecoding" with **Precision Autonomy**. 

By explicitly defining the 20 things an agent can *never* do (the BOUND), you implicitly authorize it to autonomously do the 10,000 things required to solve the problem. When an agent hits an error inside the boundary, it doesn't wait for human permission; it consults its remediation playbook, reverts, and tries a new approach.

## Structure

```
framework.py    — State management, stage transitions, verification
prepare.py      — Project scanning and initialization
modules/        — The methodology (bound, map, plan, build, verify, loop, remediation)
templates/      — Templates for CLAUDE.md and phase plans
examples/       — Real-world, anonymized examples of Ouro Loop in action
MANIFESTO.md    — The philosophy of Constraint-Driven AI Development
```

## Examples

Check out the `examples/` directory to see how Ouro Loop is applied to different domains:
- `blockchain-l1`: Guarding consensus algorithms and deterministic execution.
- `consumer-product`: Guarding user data privacy and migration state.
- `financial-system`: Guarding penny-level precision and transaction integrity.

## License
MIT
