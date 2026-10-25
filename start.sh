#!/bin/sh
# Portable npm launcher; does not kill unrelated services.
cd "$(dirname "$0")" || exit 1
exec npm run dev
