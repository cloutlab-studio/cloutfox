#!/bin/sh
# Unload and remove the AppArmor profile on removal (not on upgrade).
set -e
case "${1:-remove}" in
upgrade | 1) exit 0 ;;
esac
if [ -e /etc/apparmor.d/cloutfox ]; then
    if command -v apparmor_parser >/dev/null 2>&1 && [ -d /sys/kernel/security/apparmor ]; then
        apparmor_parser -R /etc/apparmor.d/cloutfox 2>/dev/null || true
    fi
    rm -f /etc/apparmor.d/cloutfox
fi
exit 0
