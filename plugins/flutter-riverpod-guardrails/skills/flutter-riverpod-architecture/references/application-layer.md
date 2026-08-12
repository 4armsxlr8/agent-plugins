# Application Layer Rules

## Layer Purpose

Handle business logic, state management, and Provider definitions.

## ALLOWED

- Riverpod providers and state management
- Business logic and domain orchestration
- Repository consumption and dependency injection
- `flutter_riverpod` package

## FORBIDDEN

- `package:flutter/` imports (except flutter_riverpod)
- UI classes (`BuildContext`, `Navigator`, `showDialog`, `ScaffoldMessenger`)
- Widget classes

## Provider Types

### Repository Providers (Singleton)

```dart
// Platform flags are resolved at bootstrap and injected via an override —
// the application layer never imports package:flutter/.
@Riverpod(keepAlive: true)
bool isWeb(Ref ref) => throw UnimplementedError('Overridden in main.dart');

@Riverpod(keepAlive: true)
SomeRepository someRepository(Ref ref) {
  return SomeRepository(
    firestore: ref.watch(firebaseFirestoreProvider),
    auth: ref.watch(firebaseAuthProvider),
    isWeb: ref.watch(isWebProvider),
  );
}
```

The override happens in the app entry point, which lives outside the layer
directories and is therefore free to read platform constants:

```dart
// main.dart — outside the layer directories, so kIsWeb is allowed here.
void main() {
  runApp(ProviderScope(
    overrides: [isWebProvider.overrideWithValue(kIsWeb)],
    child: const MyApp(),
  ));
}
```

### Stream Providers (Auto-dispose)

```dart
@riverpod
Stream<List<Project>> projects(Ref ref) {
  return ref.watch(projectRepositoryProvider).watchProjects();
}
// NOTE: ref.invalidate() NOT NEEDED for StreamProviders
```

### Future Providers (Auto-dispose)

```dart
@riverpod
Future<Project> projectDetail(Ref ref, String projectId) async {
  return ref.watch(projectRepositoryProvider).getProject(projectId);
}
// NOTE: ref.invalidate() REQUIRED after write operations
```

## AsyncNotifier Pattern (REQUIRED)

```dart
@riverpod
class SomeNotifier extends _$SomeNotifier {
  @override
  Future<void> build() async => null;

  Future<void> someAction({required String title}) async {
    // 1. Prevent disposal during async operation
    final link = ref.keepAlive();

    // 2. Set loading state
    state = const AsyncValue.loading();

    // 3. Execute with automatic error handling
    state = await AsyncValue.guard(() async {
      final repo = ref.read(someRepositoryProvider);
      await repo.performAction(title);
    });

    // 4. Release keepAlive
    link.close();
  }
}
```

## State Management

### RECOMMENDED: AsyncValue<T>

The server round-trip gets its own notifier. It carries no form data — the field
values are passed in as arguments — so its `AsyncValue` describes exactly one
thing: how the submission is going.

```dart
@riverpod
class ProjectSubmit extends _$ProjectSubmit {
  @override
  Future<void> build() async {}

  Future<void> submit({required String title, required String description}) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      await ref.read(projectRepositoryProvider).createProject(
        title: title,
        description: description,
      );
    });
  }
}
```

### AVOID: Custom XXXState classes

```dart
// ANTI-PATTERN: Don't manually manage loading/error
@freezed
abstract class ProjectFormState with _$ProjectFormState {
  const factory ProjectFormState({
    @Default(false) bool isLoading,  // AsyncValue handles this
    String? errorMessage,             // AsyncValue handles this
  }) = _ProjectFormState;
}
```

What is wrong here is the duplication: `isLoading` and `errorMessage` restate what
the notifier's `AsyncValue` already knows, so the two can disagree. A state class
that holds only field values is fine — it just belongs in the presentation layer.

> Boundary: any state that involves a server round-trip (fetch, submit, update) is represented as `AsyncValue` in the application layer. Only pure UI-local state (form field values, focus, expansion) may live in a custom state class in the presentation layer.

## Controller Creation Criteria

### CREATE Controller when:

- Multiple repositories need coordination
- Complex business rules apply
- Transaction management required
- Side effects need chaining

### DON'T CREATE Controller when:

- Simple CRUD to a single repository
- No additional business logic
- Would be a pass-through

**Principle**: YAGNI - Don't create until needed

## Provider Invalidation Rules

| Provider Type | After Write Operation |
|---------------|-----------------------|
| StreamProvider | No invalidation needed (auto-updates) |
| FutureProvider | `ref.invalidate()` required |
| StateProvider | Manual state update |

```dart
// After creating a project
await repository.createProject(project);
ref.invalidate(projectDetailProvider(projectId)); // Required for FutureProvider
// StreamProvider watching projects list updates automatically
```

## Custom Lint Rules (Recommended)

- `forbid_application_flutter_import`: Application layer cannot import Flutter UI classes
