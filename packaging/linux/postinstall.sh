#!/bin/sh
# Install the AppArmor profile where AppArmor 4 is present (Ubuntu 23.10+), and
# add the CloutFox repository so the system update brings new versions.
set -e
profile=/opt/cloutfox/share/apparmor/cloutfox
if [ -e /etc/apparmor.d/abi/4.0 ] && [ -e "$profile" ]; then
    cp "$profile" /etc/apparmor.d/cloutfox
    if command -v apparmor_parser >/dev/null 2>&1 && [ -d /sys/kernel/security/apparmor ]; then
        apparmor_parser -r -T -W /etc/apparmor.d/cloutfox || true
    fi
fi

# The repository is added once, on the first install: a person who deletes its
# file later keeps it deleted (the marker remembers it was added). To opt out
# before installing, put repo=no into /etc/default/cloutfox.
keys=/opt/cloutfox/share/keys
base=https://software.cloutlab.studio
marker=/var/lib/cloutfox/repo-added
if [ -e "$marker" ]; then
    exit 0
fi
if [ -r /etc/default/cloutfox ] && grep -q '^repo=no' /etc/default/cloutfox; then
    exit 0
fi
mkdir -p /var/lib/cloutfox
touch "$marker"
if [ -d /etc/apt/sources.list.d ] && command -v apt-get >/dev/null 2>&1; then
    if [ ! -e /etc/apt/sources.list.d/cloutfox.sources ] && [ ! -e /etc/apt/sources.list.d/cloutfox.list ]; then
        install -m 0644 "$keys/cloutfox.gpg" /usr/share/keyrings/cloutfox.gpg
        cat >/etc/apt/sources.list.d/cloutfox.sources <<SOURCES
Types: deb
URIs: $base/apt
Suites: stable
Components: main
Architectures: amd64
Signed-By: /usr/share/keyrings/cloutfox.gpg
SOURCES
    fi
    exit 0
fi
for repos in /etc/yum.repos.d /etc/zypp/repos.d; do
    if [ -d "$repos" ]; then
        if [ ! -e "$repos/cloutfox.repo" ]; then
            install -m 0644 "$keys/cloutfox.asc" /etc/pki/rpm-gpg/cloutfox.asc 2>/dev/null ||
                { mkdir -p /etc/pki/rpm-gpg && install -m 0644 "$keys/cloutfox.asc" /etc/pki/rpm-gpg/cloutfox.asc; }
            cat >"$repos/cloutfox.repo" <<REPO
[cloutfox]
name=CloutFox
baseurl=$base/rpm/x86_64
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/cloutfox.asc
metadata_expire=6h
REPO
        fi
        break
    fi
done
exit 0
