# Date planner

## Versioning (every push and merge)

The site shows a faded version at the bottom left, like `v0.16 10-14-18:42` (version, then the build time in Los Angeles as MM-DD-HH:MM). The number comes from `frontend/VERSION`; the time is stamped when the UI is built.

Before every push (and when merging a PR), raise `frontend/VERSION` by an amount that matches the change. Two decimals, never lower it:

- small fix, copy or style tweak: +0.01 to +0.02
- new feature or notable behavior change: +0.03 to +0.09
- major feature, big rework or schema change: +0.10 or more

Say the old and new number in the commit message or PR description. If a PR already raised it, a merge only needs another bump when other work landed on `main` in between.
