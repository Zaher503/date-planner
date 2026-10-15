# Date planner

## Versioning

The site shows a faded version at the bottom left, like `v0.26 10-14-18:42` (version, then the build time in Los Angeles as MM-DD-HH:MM). The number comes from `frontend/VERSION`; the time is stamped when the UI is built.

CD adds 0.1 to `frontend/VERSION` on every deploy to `main`, builds the images with the new number, and commits it back to `main` (`Bump version to vX.XX [skip ci]`). Do not edit `frontend/VERSION` by hand or bump it in a PR; the bot's commit would conflict with it. The number only shows on a deployed build; the dev and mock servers show whatever is in the file.
