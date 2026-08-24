# Changelog

## Unreleased

- Added the MIT License, author information, contribution guidance, repository CI, and private security reporting.

## 0.8.3

- Resolved the active profile home through Hermes, including profiles served by a shared gateway.
- Added per-profile installation guidance, a post-install verification message, and architecture documentation.
- Kept the plugin manifest compatible with the current Hermes installer.
- Replaced workspace-specific identifiers in portability tests.

## 0.8.2

- Rejected generated review content as the sole basis for a USER fact.
- Accepted autonomous USER learning only when a prior user message or independently verified source supports it.
- Preserved foreground learning and Curator ownership.

## 0.8.1

- Restored Hermes's native skill-read marker in the matching background tool context.
- Allowed one retry for the same skill owner and exact file.
- Blocked owner or file switching, MEMORY fallbacks, direct learning-file edits, and mutating Curator terminal commands.
- Stopped autonomous learning at state capacity instead of evicting active work.

## 0.8.0

- Registered guidance and policy checks before and after selected Hermes calls.
- Applied separate rules to foreground work, automatic review, and Curator maintenance.
- Kept Hermes's native tools as the only durable learning writers.
