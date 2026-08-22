# Changelog

User-facing source changes live here. No public release or version tag exists yet.

## 0.8.3

- Resolved profile homes through Hermes so direct-file checks stay correct when one gateway serves several profiles.
- Replaced the implementation notes with a short public README.
- Explained single-agent and multi-agent use. Each profile runs its own isolated plugin copy.
- Added a short message shown after Hermes installs the plugin.
- Added plain-language architecture docs and a full-size technical diagram.
- Kept the manifest in the format accepted by the current Hermes installer.
- Replaced local project names in portability tests with neutral examples.

## 0.8.2

- Stopped automatic review instructions, plugin text, system text, skills, assistant replies, and tool results from becoming USER preferences by themselves.
- Kept automatic USER learning available when a real user message or another trusted source supports it.
- Left regular user work and Curator ownership unchanged.

## 0.8.1

- Carried one confirmed skill read into the matching background write call.
- Limited recovery to one retry for the same skill and exact file.
- Blocked filename switches, sibling skills, MEMORY workarounds, direct file edits, and mutating Curator shell commands.
- Refused automatic learning when short-lived state was full instead of dropping active work.

## 0.8.0

- Added guidance before model turns and checks before and after selected tool calls.
- Added separate rules for regular work, automatic review, and Curator.
- Kept Hermes as the only durable learning writer.
