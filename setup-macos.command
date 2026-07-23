#!/bin/bash
set -u

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT" || exit 1

/bin/bash "$PROJECT_ROOT/setup.sh" "$@"
STATUS=$?

printf '\n'
if ((STATUS == 0)); then
    printf 'macOS setup finished successfully.\n'
else
    printf 'macOS setup stopped with an error.\n' >&2
fi

if [[ -t 0 ]]; then
    read -r -p "Press Return to close this window..." _
fi

exit "$STATUS"
