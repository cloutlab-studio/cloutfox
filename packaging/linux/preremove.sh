#!/bin/sh
# On removal (not on upgrade): unload the AppArmor profile and take the
# repository away with the package.
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
rm -f /etc/apt/sources.list.d/cloutfox.sources /usr/share/keyrings/cloutfox.gpg \
    /etc/yum.repos.d/cloutfox.repo /etc/zypp/repos.d/cloutfox.repo /etc/pki/rpm-gpg/cloutfox.asc
rm -rf /var/lib/cloutfox
exit 0
