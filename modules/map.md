# Stage 1: MAP — Understand the Problem Space

Before planning any solution, understand the territory you're operating in.

## Why Map First

The most common cause of scope creep and rework is starting to build before
understanding the full problem space. MAP forces you to look before you leap.

## The Six Dimensions

### 1. User Mental Model

How does the end user think about this?

- What terminology do they use?
- What's their expectation of how this should work?
- What would surprise or confuse them?

This prevents building technically correct but user-hostile features.

### 2. Attack Surface

What could go wrong?

- What are the edge cases?
- What are the failure modes?
- What are the security implications?
- What happens under load?
- What happens with bad input?

List at least 3 failure scenarios before proceeding.

### 3. Bottlenecks

What are the constraints?

- Performance: response time, throughput, memory
- Complexity: algorithmic, state management, concurrency
- External: API limits, service dependencies, data volume

Identify the tightest constraint — it drives architecture decisions.

### 4. Dependencies

What existing code/systems does this touch?

- Direct dependencies: files that must be modified
- Indirect dependencies: files that import/use modified code
- External dependencies: services, APIs, databases
- Build dependencies: CI/CD, deployment pipelines

Map the dependency graph. Surprises here cause the most rework.

### 5. Reusable Assets

What already exists that can be leveraged?

- Existing utilities, helpers, base classes
- Similar features already implemented
- Patterns established in the codebase
- Third-party libraries already in use

Don't build what you can reuse. Check before creating.

### 6. Core Metric

What single metric best indicates success?

- For a bug fix: the specific test case that should pass
- For a feature: the user action that should work
- For a refactor: the code quality metric that should improve
- For performance: the specific benchmark number

Define it concretely: "Response time for /api/users < 200ms at p99."

## MAP Output

After mapping, you should have a clear picture:

```
Task: [description]
User expects: [mental model summary]
Risk: [top 3 failure scenarios]
Constraint: [tightest bottleneck]
Touches: [list of affected systems]
Reuses: [existing assets to leverage]
Metric: [concrete success criterion]
```

## When to Skip MAP

For Trivial complexity (single file, <20 lines, obvious fix), MAP can be
implicit — just verify the fix is correct and move to BUILD.

For everything else, take 5 minutes to MAP. It saves hours of rework.
