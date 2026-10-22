#  Copyright 2026 Cisco Systems, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Argument checks for the ona-capture-* wrappers. The wrappers run as root
# under obsrvbl_ona.sudoers, and their arguments come from configuration the
# service user can write, so every argument is checked. Each check exits on
# failure.

ONA_USER="obsrvbl_ona"
ONA_NET_DIR="/sys/class/net"
ONA_LOG_DIR="/opt/obsrvbl-ona/logs"

ona_die() {
    echo "$0: $*" >&2
    exit 64
}

# $1 must name an interface the kernel has.
ona_require_iface() {
    case "$1" in
        '' | '.' | '..' | -* | *[!A-Za-z0-9._-]*)
            ona_die "not an interface name: '$1'"
            ;;
    esac

    if [ ! -e "${ONA_NET_DIR}/$1" ]; then
        ona_die "no such interface: '$1'"
    fi
}

# As ona_require_iface, but also accepts tcpdump's "any".
ona_require_capture_iface() {
    if [ "$1" != "any" ]; then
        ona_require_iface "$1"
    fi
}

# $1 must be a decimal integer in [$2, $3], with no leading zeros.
ona_require_integer() {
    case "$1" in
        '' | *[!0-9]*)
            ona_die "not a number: '$1'"
            ;;
        0 | [1-9]*)
            ;;
        *)
            ona_die "leading zeros are not allowed: '$1'"
            ;;
    esac

    if [ "${#1}" -gt 10 ]; then
        ona_die "number is too long: '$1'"
    fi

    if [ "$1" -lt "$2" ] || [ "$1" -gt "$3" ]; then
        ona_die "$1 is outside [$2, $3]"
    fi
}

# $1 must contain only address characters, so it cannot become an option.
ona_require_network() {
    case "$1" in
        '' | -* | *[!0-9A-Fa-f.:/]*)
            ona_die "not a network: '$1'"
            ;;
    esac
}

# Sets ONA_BPF to a capture filter for the networks in "$@", or to the
# empty string when there are none.
ona_build_bpf() {
    ONA_BPF=""

    for _ona_network in "$@"; do
        ona_require_network "$_ona_network"

        if [ -n "$ONA_BPF" ]; then
            ONA_BPF="${ONA_BPF} or "
        fi

        ONA_BPF="${ONA_BPF}(net ${_ona_network})"
    done
}

# Sets ONA_LOG_PATH to $1 without a trailing slash, and exits unless it is
# ${ONA_LOG_DIR}/$2, the directory this wrapper's pusher reads.
ona_require_log_dir() {
    ONA_LOG_PATH="${1%/}"

    if [ "$ONA_LOG_PATH" != "${ONA_LOG_DIR}/$2" ]; then
        ona_die "not this program's log directory: '$1'"
    fi
}

# Brings the interface up in promiscuous mode. Not fatal, as before.
ona_set_promisc() {
    /sbin/ifconfig "$1" up promisc || true
}
