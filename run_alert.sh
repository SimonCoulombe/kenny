#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python get_lanewatch.py  2>>lanewatch.log
.venv/bin/python get_my_cars.py    2>>lanewatch.log
.venv/bin/python get_audi_xenon.py 2>>lanewatch.log
output=$(.venv/bin/python generate_report.py)
echo "$output" > report.html
if echo "$output" | grep -q '★ NEW'; then
    new_count=$(echo "$output" | grep -c '★ NEW')
    echo "$output" | mail \
        -s "Kenny U-Pull — ${new_count} new vehicle$([ "$new_count" -eq 1 ] && echo '' || echo 's')" \
        -a "MIME-Version: 1.0" \
        -a "Content-Type: text/html; charset=UTF-8" \
        simoncoulombe@protonmail.com
fi
