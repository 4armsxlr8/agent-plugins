---
name: architecture
description: Clean Architecture patterns for Flutter with Riverpod state management. Use when building or reviewing Flutter apps with layered architecture (Domain, Data, Application, Presentation).
paths: "lib/**/*.dart"
metadata:
  purpose: knowledge
  trigger: user
  shape: atomic
  kind: manual
---

# Flutter + Riverpod Clean Architecture

## Overview

This skill provides architectural patterns and rules for building Flutter applications using Clean Architecture with Riverpod for state management. Follow these patterns to maintain clear layer boundaries, testability, and scalability.

## Architecture Layers

Dependencies point inward: Presentation -> Application -> Data -> Domain.

| Layer | Purpose & Key Technology | Can Depend On | Cannot Depend On |
|-------|--------------------------|---------------|------------------|
| **Domain** | Business entities and Value Objects. Freezed, pure Dart | Nothing (pure Dart) | Flutter, Riverpod, Firebase, any SDK |
| **Data** | Repository implementations and external calls. Firebase, HTTP clients | Domain | Flutter, Riverpod, Presentation |
| **Application** | State management and provider definitions. Riverpod, AsyncNotifier | Domain, Data | Flutter UI classes (`BuildContext`, `Navigator`, `kIsWeb`) |
| **Presentation** | UI components and routing. ConsumerWidget, go_router | Application, Domain | Data (direct repository access) |

## House Rules

These are the project-specific calls this skill makes. They are not generic Clean Architecture advice.

1. **No abstract interface for repositories.** Every Dart class already defines an implicit interface, and tests swap implementations through a provider override, so a second abstract class only adds a file to keep in sync.
2. **Widget classes, never widget-returning functions.** A `const` widget class lets Flutter skip rebuilds and keeps its identity stable across hot reload; a `_buildXxx()` method gives up both.
3. **Platform constants are resolved at bootstrap and injected as `bool`.** `kIsWeb` lives in `package:flutter/foundation.dart`, so reading it inside the data or application layer would break those layers' purity. `main.dart` reads it once and injects it via a provider override.
4. **Boundary: any state that involves a server round-trip (fetch, submit, update) is represented as `AsyncValue` in the application layer. Only pure UI-local state (form field values, focus, expansion) may live in a custom state class in the presentation layer.**

## Directory Structure (Recommended)

```
lib/
├── app/
│   ├── route/           # go_router configuration
│   └── providers/       # App-wide providers
├── features/
│   └── {feature}/
│       ├── domain/      # Entities, Value Objects
│       ├── data/        # Repositories
│       ├── application/ # Providers, Notifiers
│       └── presentation/# Screens, Widgets
│           └── providers/  # UI-local state notifiers
└── shared/
    ├── domain/          # Shared entities
    ├── data/            # Shared repositories
    └── widgets/         # Shared UI components
```

## Getting Started

1. **New Entity?** -> See `references/domain-layer.md`
2. **API Integration?** -> See `references/data-layer.md`
3. **State Management?** -> See `references/application-layer.md`
4. **Building UI?** -> See `references/presentation-layer.md`
5. **Widget Patterns?** -> See `references/ui-patterns.md`
6. **Enforce layer boundaries with lint?** -> See the `lint-setup` skill

## Gotchas

- **Freezed 3.x requires a modifier on every class with a factory constructor.** Use `@freezed abstract class X with _$X` for data classes and `@freezed sealed class X with _$X` for union types. Without the modifier the generated code fails to compile.
- **Missing `part` declarations produce silent no-ops.** If `part 'x.freezed.dart';` or `part 'x.g.dart';` is absent, `build_runner` generates nothing for that file, and the resulting errors point at the usage site rather than the cause.
- **Use `ref.read` inside event handlers and callbacks, never `ref.watch`.** `ref.watch` is only valid during `build`; calling it from an `onPressed` closure sets up a subscription that will not behave as intended.
- **go_router_builder 4.x requires the generated mixin on every route class.** Write `class HomeRoute extends GoRouteData with $HomeRoute` — the mixin was renamed from `_$RouteName` to the public `$RouteName` in 4.0.0.

## Compliance Verification

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/check-architecture.sh --scan lib
```

The script walks all of `lib/` (both `lib/shared/` and `lib/features/`), applies the rules for whichever layer each file sits in, and skips generated files (`*.freezed.dart`, `*.g.dart`). Every violation is reported with the file path it was found in, plus a line number for function-style widget hits; the script exits non-zero when anything is reported.
