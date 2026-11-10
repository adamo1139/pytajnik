#!/usr/bin/env bash
# Zatrzymuje procesy zapisane przez uruchom.sh (po PID, w odwrotnej kolejności).
cd "$(dirname "$0")"
[[ -f logi/pids ]] || { echo "brak logi/pids"; exit 0; }
tac logi/pids | while read -r pid name; do
    if kill "${pid}" 2> /dev/null; then echo "zatrzymano ${name} (${pid})"; fi
done
rm -f logi/pids
