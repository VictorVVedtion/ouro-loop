# Example: Consumer Product

This example shows how Ouro Loop's BOUND system applies to a creative collaboration platform for musicians — an iOS/macOS app with real-time audio streaming, project sharing, and version control for audio tracks. The BOUND definition protects the audio engine, CRDT-based conflict resolution, in-app purchase logic, and Core Data model. A real session using this BOUND demonstrated how the ROOT_CAUSE gate prevented a lazy fix and pushed the agent toward a genuinely better architectural pattern.

---

## Project Overview

| | |
|---|---|
| **Project** | MusicApp — Creative Collaboration Platform |
| **Language** | Swift/SwiftUI, TypeScript (Next.js frontend) |
| **Architecture** | AVAudioEngine for audio, CloudKit + CRDT for sync, StoreKit 2 for IAP, Core Data persistence |
| **Session task** | Eliminate all ESLint errors to establish clean lint baseline |

---

## BOUND Definition

### DANGER ZONES

| Path | Risk |
|------|------|
| `Sources/Audio/Engine/` | Core audio engine. Crashes here = audio glitches during live sessions. |
| `Sources/Sync/ConflictResolver.swift` | CRDT-based conflict resolution. Wrong merge = data loss. |
| `Sources/IAP/` | In-app purchases. Apple review compliance critical. |
| `CoreData/Model.xcdatamodeld` | Core Data model. Migration errors = user data loss. |

### NEVER DO

- Never block the audio thread with synchronous I/O or network calls
- Never change Core Data model without a tested migration mapping
- Never modify IAP product identifiers — App Store rejects are expensive
- Never ship without testing on the minimum supported iOS version
- Never silently drop audio frames — always notify the user
- Never store audio files in the app bundle — use Documents or iCloud

### IRON LAWS

- Audio callback latency never exceeds 10ms
- Core Data migrations are tested with production-schema snapshots
- All network requests have timeout and retry logic
- UI updates happen only on MainActor
- Audio format conversions preserve sample rate and bit depth
- App launch to interactive time under 2 seconds on iPhone 13

---

## Development Workflow

```bash
# Build
xcodebuild -scheme MusicApp -destination 'platform=iOS Simulator,name=iPhone 15'

# Test
xcodebuild test -scheme MusicApp -destination 'platform=iOS Simulator,name=iPhone 15'

# Audio Latency Test
swift test --filter AudioLatencyTests
```

---

## Session Highlights

The session targeted ESLint error remediation in the React/Next.js frontend component of the app:

| Metric | Before | After |
|--------|--------|-------|
| Lint errors | 3 | 0 |
| Lint warnings | 3 | 3 (unchanged) |
| Build status | Pass | Pass (IRON LAW maintained) |
| Remediations | — | 1 autonomous remediation |

Key methodology observations:

1. **ROOT_CAUSE gate caught a lazy fix** — the first attempt restructured a `useEffect` but still called `setState` inside it. The React Compiler's `set-state-in-effect` rule rejected it. The gate correctly identified this as symptom-patching.
2. **The derived state pattern was superior** — the final fix eliminated the `useEffect` entirely, replacing `useState + useEffect` with a pure derived value. This is not just lint-clean but architecturally better — React's mental model prefers computed values over synchronized state.
3. **Simple complexity was correct** — the task touched 2 files, no DANGER ZONE. The complexity router in `program.md` correctly classified this as "execute directly" — no phase plan needed.
4. **IRON LAW verification caught nothing but provided confidence** — running `next build` after every change confirmed the build pass IRON LAW held throughout.

[:material-file-document: Full Session Log](../session-logs/consumer-product.md)

---

## What the BOUND Teaches

This consumer product BOUND demonstrates several patterns:

- **DANGER ZONES protect real-time and financial code**: the audio engine has strict latency requirements, and IAP modifications risk App Store rejection — both are irreversible in production.
- **NEVER DO rules prevent platform-specific mistakes**: blocking the audio thread or storing files in the app bundle are iOS-specific antipatterns that cause hard-to-debug production failures.
- **IRON LAWS are performance-measurable**: audio latency thresholds, launch time targets, and format conversion accuracy are all programmatically verifiable.
- **Even simple tasks benefit from verification**: the ROOT_CAUSE gate turned a "good enough" fix into a genuinely better solution by rejecting the first symptom-level attempt.
