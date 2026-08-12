# Presentation Layer Rules

## Layer Purpose

Handle UI components, widgets, screens, and route guards.

## ALLOWED

- Full Flutter framework access
- UI state management (presentation layer notifiers)
- User interactions
- go_router integration
- Design system tokens

## FORBIDDEN - Direct Data Layer Access

```dart
// FORBIDDEN - Direct Data layer access
import 'package:myapp/features/*/data/*_repository.dart';

// FORBIDDEN - Calling Repository directly
final repository = ProjectRepository(...);
await repository.createProject(...);
```

Presentation layer accesses data ONLY through Application layer Providers.

## Screen with ConsumerWidget

```dart
class ProjectListScreen extends ConsumerWidget {
  const ProjectListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectsAsync = ref.watch(projectListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Projects')),
      body: projectsAsync.when(
        data: (projects) => ListView.builder(
          itemCount: projects.length,
          itemBuilder: (context, index) => ProjectCard(
            project: projects[index],
            onTap: () => ProjectDetailRoute(
              projectId: projects[index].id,
            ).push(context),
          ),
        ),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, stack) => Center(child: Text('Error: $error')),
      ),
    );
  }
}
```

## Type-Safe Routing (go_router)

Requires go_router_builder 4.x (the generated mixin was renamed from
`_$RouteName` to `$RouteName` in 4.0.0).

```dart
// lib/app/route/routes.dart
part 'routes.g.dart';

@TypedGoRoute<ProjectListRoute>(
  path: '/projects',
  routes: [
    TypedGoRoute<ProjectDetailRoute>(path: ':projectId'),
  ],
)
class ProjectListRoute extends GoRouteData with $ProjectListRoute {
  const ProjectListRoute();

  @override
  Widget build(BuildContext context, GoRouterState state) {
    return const ProjectListScreen();
  }
}

class ProjectDetailRoute extends GoRouteData with $ProjectDetailRoute {
  const ProjectDetailRoute({required this.projectId});

  final String projectId;

  @override
  Widget build(BuildContext context, GoRouterState state) {
    return ProjectDetailScreen(projectId: projectId);
  }
}

// Usage
ProjectDetailRoute(projectId: 'abc123').push(context);
```

## UI State Notifier (Presentation Layer Provider)

> Boundary: any state that involves a server round-trip (fetch, submit, update) is represented as `AsyncValue` in the application layer. Only pure UI-local state (form field values, focus, expansion) may live in a custom state class in the presentation layer.

```dart
// presentation/providers/project_form_notifier.dart
// Holds UI-local state only: field values being edited.
@freezed
abstract class ProjectFormState with _$ProjectFormState {
  const factory ProjectFormState({
    @Default('') String title,
    @Default('') String description,
  }) = _ProjectFormState;
}

@riverpod
class ProjectFormNotifier extends _$ProjectFormNotifier {
  @override
  ProjectFormState build() => const ProjectFormState();

  void updateTitle(String title) => state = state.copyWith(title: title);
  void updateDescription(String value) => state = state.copyWith(description: value);
}
```

```dart
// Submission goes through the application layer; its AsyncValue carries
// loading/error so the form state never duplicates them.
class SubmitButton extends ConsumerWidget {
  const SubmitButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final submitState = ref.watch(projectSubmitProvider);

    return FilledButton(
      onPressed: submitState.isLoading
          ? null
          : () {
              final form = ref.read(projectFormNotifierProvider);
              ref.read(projectSubmitProvider.notifier).submit(
                    title: form.title,
                    description: form.description,
                  );
            },
      child: submitState.isLoading
          ? const CircularProgressIndicator()
          : const Text('Submit'),
    );
  }
}
```

## select() Optimization

```dart
// BAD - Watches entire object (unnecessary rebuilds)
final user = ref.watch(userProvider);
Text(user.name);

// GOOD - Watches only needed field
final userName = ref.watch(userProvider.select((u) => u.name));
Text(userName);
```

## Layer Compliance Checklist

Before submitting presentation code, verify:

1. [ ] Not importing Data layer (`*_repository.dart`) directly
2. [ ] Accessing data through Application layer Providers
3. [ ] Using go_router type-safe routing
4. [ ] Using `select()` to watch only needed data

## Verification

Run the checker bundled with this plugin from the Flutter project root. Replace
`<plugin root>` with the `flutter-riverpod-guardrails` plugin directory — SKILL.md
shows the resolved absolute path while this skill is active.

```bash
<plugin root>/scripts/check-architecture.sh --scan lib
```

## Related References

- `ui-patterns.md` - Widget class patterns, ConsumerWidget usage
