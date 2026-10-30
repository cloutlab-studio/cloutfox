#!/bin/sh
# Install the AppArmor profile where AppArmor 4 is present (Ubuntu 23.10+).
set -e
profile=/opt/cloutfox/share/apparmor/cloutfox
if [ -e /etc/apparmor.d/abi/4.0 ] && [ -e "$profile" ]; then
    cp "$profile" /etc/apparmor.d/cloutfox
    if command -v apparmor_parser >/dev/null 2>&1 && [ -d /sys/kernel/security/apparmor ]; then
        apparmor_parser -r -T -W /etc/apparmor.d/cloutfox || true
    fi
fi
exit 0
