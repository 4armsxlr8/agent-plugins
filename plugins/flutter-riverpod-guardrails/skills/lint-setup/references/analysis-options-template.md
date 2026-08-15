# analysis_options.yaml Template

Copy this into the project's `analysis_options.yaml` and replace every
`<package_name>` with the `name:` value from `pubspec.yaml`. The placeholder
appears 8 times. Versions below are what was measured working in 2026-08 on Dart
3.12.2.

```yaml
include: package:flutter_lints/flutter.yaml

plugins:
  import_lint:
    version: ^2.0.0
    diagnostics:
      import_lint: error

  riverpod_lint:
    version: ^3.1.4
    diagnostics:
      async_value_nullable_pattern: warning
      avoid_build_context_in_providers: warning
      avoid_public_notifier_properties: warning
      avoid_ref_inside_state_dispose: warning
      functional_ref: warning
      missing_provider_scope: warning
      notifier_build: warning
      notifier_extends: warning
      only_use_keep_alive_inside_keep_alive: warning
      protected_notifier_properties: warning
      provider_dependencies: warning
      provider_parameters: warning
      riverpod_syntax_error: warning
      scoped_providers_should_specify_dependencies: warning
      unsupported_provider_value: warning

import_lint:
  severity: "error"
  rules:
    domain_no_flutter:
      target: "package:<package_name>/features/*/domain/**"
      from: "package:flutter/**"
      except: []
    domain_no_riverpod:
      target: "package:<package_name>/features/*/domain/**"
      from: "package:flutter_riverpod/**"
      except: []
    domain_no_firestore:
      target: "package:<package_name>/features/*/domain/**"
      from: "package:cloud_firestore/**"
      except: []
    data_no_flutter:
      target: "package:<package_name>/features/*/data/**"
      from: "package:flutter/**"
      except: []
    data_no_riverpod:
      target: "package:<package_name>/features/*/data/**"
      from: "package:flutter_riverpod/**"
      except: []
    application_no_flutter:
      target: "package:<package_name>/features/*/application/**"
      from: "package:flutter/**"
      except: []
    presentation_no_data:
      target: "package:<package_name>/features/*/presentation/**"
      from: "package:<package_name>/features/*/data/**"
      except: []
```

## The `plugins:` block

This is the Dart 3.10+ analyzer plugin mechanism. Plugins listed here are resolved
by the analysis server in its own pub solve under `~/.dartServer/.plugin_manager/`,
separate from the project's pubspec. Two consequences:

- A plugin does not need to be in `dev_dependencies`. That is what makes
  riverpod_lint usable at all here — `flutter pub add --dev riverpod_lint` cannot
  resolve, because flutter_riverpod 3.x pulls in riverpod, riverpod depends on
  `test ^1.0.0`, and the SDK's flutter_test pins `test_api` to a version that in
  turn pins analyzer below the `^13` that riverpod_lint 3.1.6+ wants.
- The plugins must be resolvable **with each other**. `^3.1.4` lets the joint solve
  fall back to 3.1.4 or 3.1.5, which still accept the `analyzer ^12.1.0` that
  import_lint 2.0.0 requires. riverpod_lint 3.1.6+ requires `analyzer ^13.0.0`, so
  a floor of `^3.1.8` fails outright: no version in that range works with analyzer
  12. This is a 2026-08 constraint — once import_lint supports analyzer 13, the pin
  can be lifted.

## The `diagnostics:` blocks

`diagnostics:` is what raises severity. Without it every plugin diagnostic is
reported at `info`, `dart analyze` exits 0, and the pre-commit hook (which counts
`error`/`warning` lines) lets the commit through.

Two things that do **not** work, both measured:

- `analyzer: errors: import_lint: error` — the analyzer reports the code as
  unrecognized. This is what the import_lint README recommends.
- A wildcard such as `"*": warning` inside `diagnostics:` — ignored. Hence the 15
  riverpod_lint rules are listed individually above.

Layer boundaries are set to `error` because they are hard rules that should fail
the build. The riverpod_lint rules are `warning`, which the pre-commit hook still
counts and blocks on.

## The `import_lint:` rules

Each rule is a pair of globs over `package:` URIs. `target` selects the files the
rule applies to, `from` the imports those files may not have. Relative imports such
as `../data/foo.dart` are resolved to their `package:` URI before matching, so they
are caught the same way.

The rules encode the four-layer dependency direction. **The `architecture` skill is
the source of truth for what each layer may depend on; the table below only
restates it as globs.** If a layer rule changes, update both places.

| Rule | Enforces |
|------|----------|
| `domain_no_flutter` | Domain stays pure Dart — no `package:flutter`. |
| `domain_no_riverpod` | Domain has no state-management dependency. |
| `domain_no_firestore` | Domain has no SDK or infrastructure dependency. |
| `data_no_flutter` | Data depends on domain only; platform values such as `kIsWeb` are injected, not imported. |
| `data_no_riverpod` | Data classes are plain Dart, wired up by providers in the application layer. |
| `application_no_flutter` | Application holds state, not UI; `flutter_riverpod` is allowed, `package:flutter` is not. |
| `presentation_no_data` | Presentation goes through the application layer, never straight to a repository. |

`except: []` is the empty allow-list for each rule. Add import paths there to carve
out a specific exemption.

The top-level `severity: "error"` key applies only to the `dart run import_lint`
CLI. The severity `dart analyze` reports comes from the `diagnostics:` block.
