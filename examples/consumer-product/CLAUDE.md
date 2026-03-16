# Project: MusicApp — Creative Collaboration Platform

## Overview

iOS/macOS app for musicians to collaborate on music production. Real-time audio
streaming, project sharing, and version control for audio tracks.

## BOUND

### DANGER ZONES

- `Sources/Audio/Engine/` — Core audio engine. Crashes here = audio glitches during live sessions.
- `Sources/Sync/ConflictResolver.swift` — CRDT-based conflict resolution. Wrong merge = data loss.
- `Sources/IAP/` — In-app purchases. Apple review compliance critical.
- `CoreData/Model.xcdatamodeld` — Core Data model. Migration errors = user data loss.

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

## Architecture

- Swift/SwiftUI frontend, Core Data persistence
- AVAudioEngine for audio processing
- CloudKit for sync, CRDT for conflict resolution
- StoreKit 2 for in-app purchases

## Development Workflow

### Build
```bash
xcodebuild -scheme MusicApp -destination 'platform=iOS Simulator,name=iPhone 15'
```

### Test
```bash
xcodebuild test -scheme MusicApp -destination 'platform=iOS Simulator,name=iPhone 15'
```

### Audio Latency Test
```bash
swift test --filter AudioLatencyTests
```
