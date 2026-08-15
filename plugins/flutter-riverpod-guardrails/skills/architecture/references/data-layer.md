# Data Layer Rules

## Layer Purpose

Handle external data sources (Firebase, HTTP, etc.) as a Pure Dart layer.

## ALLOWED

- Pure Dart implementation
- External SDKs (Firebase, HTTP clients, etc.)
- Pure Dart domain models and value objects

## FORBIDDEN

- `package:flutter/` imports
- `@riverpod` annotations or Riverpod dependencies
- UI classes (`BuildContext`, `Navigator`, `showDialog`, etc.)
- `kIsWeb` and other platform-dependent constants

## Constructor Pattern

```dart
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

class SomeRepository {
  // REQUIRED: const constructor + required dependencies
  const SomeRepository({
    required FirebaseFirestore firestore,
    required FirebaseAuth auth,
    required bool isWeb,  // Platform check injected from application layer
  })  : _firestore = firestore,
        _auth = auth,
        _isWeb = isWeb;

  final FirebaseFirestore _firestore;
  final FirebaseAuth _auth;
  final bool _isWeb;
}
```

## Dependency Injection

### BAD - Direct platform dependency

```dart
class AuthRepository {
  Future<UserCredential?> signInWithGoogle() {
    if (kIsWeb) { // FORBIDDEN: Flutter dependency
      return _auth.signInWithPopup(GoogleAuthProvider());
    }
  }
}
```

### GOOD - Injected dependency

```dart
import 'package:firebase_auth/firebase_auth.dart';

class AuthRepository {
  const AuthRepository({
    required FirebaseAuth firebaseAuth,
    required bool isWeb,  // Injected from application layer
  })  : _auth = firebaseAuth,
        _isWeb = isWeb;

  final FirebaseAuth _auth;
  final bool _isWeb;

  Future<UserCredential> signInWithGoogle() {
    if (_isWeb) {  // Uses injected value
      return _auth.signInWithPopup(GoogleAuthProvider());
    }
    return _auth.signInWithProvider(GoogleAuthProvider());
  }
}
```

## Firestore Timestamp Conversion

`Timestamp` is a `cloud_firestore` symbol, and the domain layer is forbidden from
importing that SDK. So domain entities hold a plain `DateTime`, and the repository
converts at the boundary: every `Timestamp` in a snapshot becomes an ISO8601 string
before the map reaches `fromJson`, because that is the format `json_serializable`
parses into `DateTime` by default.

```dart
import 'package:cloud_firestore/cloud_firestore.dart';

/// Flattens a snapshot into JSON the domain entity can parse:
/// document id folded in, every `Timestamp` replaced by an ISO8601 string.
Map<String, dynamic> decodeDoc(DocumentSnapshot<Map<String, dynamic>> doc) {
  final raw = {...doc.data()!, 'id': doc.id};
  return raw.map(
    (key, value) => MapEntry(
      key,
      value is Timestamp ? value.toDate().toUtc().toIso8601String() : value,
    ),
  );
}
```

Write operations go the other way: convert any `DateTime` the repository itself
sets back into a `Timestamp`, so Firestore stores its native timestamp type and
`orderBy` on that field keeps working.

## Repository Pattern

```dart
class ProjectRepository {
  const ProjectRepository({
    required FirebaseFirestore firestore,
  }) : _firestore = firestore;

  final FirebaseFirestore _firestore;

  CollectionReference<Map<String, dynamic>> get _collection =>
      _firestore.collection('projects');

  /// Watch all projects as a stream
  Stream<List<Project>> watchProjects() {
    return _collection
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((snapshot) =>
            snapshot.docs.map((doc) => Project.fromJson(decodeDoc(doc))).toList());
  }

  /// Get a single project by ID
  Future<Project> getProject(String id) async {
    final doc = await _collection.doc(id).get();
    if (!doc.exists) {
      throw Exception('Project not found: $id');
    }
    return Project.fromJson(decodeDoc(doc));
  }

  /// Create a new project
  Future<String> createProject(Project project) async {
    final doc = await _collection.add(project.toJson());
    return doc.id;
  }

  /// Update an existing project
  Future<void> updateProject(Project project) async {
    await _collection.doc(project.id).update(project.toJson());
  }

  /// Delete a project
  Future<void> deleteProject(String id) async {
    await _collection.doc(id).delete();
  }
}
```

## No Separate Interface (Abstract Class)

Do not define a separate abstract class as an interface for repositories.
Every Dart class implicitly defines an interface
([implicit interfaces](https://dart.dev/language/classes#implicit-interfaces)),
so a concrete class is enough. Swappability is achieved by overriding the
provider in the application layer during tests — DIP-style interfaces are
unnecessary in app code.

### BAD - Redundant abstract interface

```dart
abstract class ProjectRepositoryInterface {
  Stream<List<Project>> watchProjects();
}

class ProjectRepository implements ProjectRepositoryInterface {
  @override
  Stream<List<Project>> watchProjects() { /* ... */ }
}
```

### GOOD - Concrete class only

```dart
class ProjectRepository {
  Stream<List<Project>> watchProjects() { /* ... */ }
}
```

In tests, `implements` the concrete class directly (extending `Fake` allows
leaving unrelated methods unimplemented):

```dart
class FakeProjectRepository extends Fake implements ProjectRepository {
  @override
  Stream<List<Project>> watchProjects() => Stream.value([sampleProject]);
}

// Swap via provider override (application layer)
final container = ProviderContainer(
  overrides: [
    projectRepositoryProvider.overrideWith((ref) => FakeProjectRepository()),
  ],
);
```

## Verification

Run the checker bundled with this plugin from the Flutter project root. Replace
`<plugin root>` with the `flutter-riverpod-guardrails` plugin directory — SKILL.md
shows the resolved absolute path while this skill is active.

```bash
<plugin root>/scripts/check-architecture.sh --scan lib
```

## Custom Lint Rules (Recommended)

- `forbid_data_upper_imports`: Data layer cannot import presentation/application/Flutter
- `avoid_provider_in_data_layer`: Data layer cannot use Riverpod
