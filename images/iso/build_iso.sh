#!/bin/bash -x

#  Copyright 2015 Observable Networks
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
#
# Build an Ubuntu-based ONA installation disc.
#
# Note of experience:
#  - This is usually a very temperamental process, expect things to go
#    wrong.
#

#    ubuntu-22.04.4-live-server-amd64.iso

RELEASE="${RELEASE:-22.04.4}"
ARCH="${ARCH:-amd64}"
VARIANT="${VARIANT:-subiquity}"


DIR=$(cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd)

fatal() {
    echo "$@" >&2
    exit 1
}

while getopts "f:a:r:" opt ; do
    case $opt in
        f) url="file://$(readlink -f $OPTARG)"
           ;;
        a) ARCH="$OPTARG"
           ;;
        r) RELEASE="$OPTARG"
           ;;
        ?) fatal "invalid argument"
           ;;
    esac
done

ubuntu_name="ubuntu-${RELEASE}-server-${ARCH}.iso"
ona_name="ona-${RELEASE}-server-${ARCH}.iso"
ubuntu_url="${url:-$($DIR/build_iso_helper $RELEASE $VARIANT)}"
test -n "$ubuntu_url" || fatal "failed getting Ubuntu ISO download URL"
ona_service_url="https://s3.amazonaws.com/onstatic/ona-service/master/ona-service_UbuntuXenial_amd64.deb"
netsa_pkg_url="https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb"

shift $(($OPTIND-1))

test $EUID -ne 0 && sudo="sudo"
which mkisofs 1> /dev/null || fatal "missing mkisofs: $sudo apt-get install genisoimage"
which isohybrid 1> /dev/null || fatal "missing isohybrid: $sudo apt-get install syslinux-utils"

[[ -d "$DIR" ]] || fatal  # invalid directory
[[ -d "$DIR"/working && $(ls -A "$DIR"/working) ]] && fatal  # working directory exists and is not empty
[[ -d "$DIR"/working ]] || mkdir "$DIR"/working # working directory does not exist, so create it
(
  set -e
  cd "$DIR"/working
  curl -L -o ${ubuntu_name} "${ubuntu_url}"
  curl -L -o netsa-pkg.deb "${netsa_pkg_url}"
  curl -L -o ona-service.deb "${ona_service_url}"
  mkdir cdrom local

  $sudo mount -o loop --read-only "${ubuntu_name}" cdrom
  rsync -av --quiet cdrom/ local

  $sudo cp ../preseed/* local/preseed/
  $sudo cp -r ../ona local


  $sudo cp netsa-pkg.deb local/ona/netsa-pkg.deb
  $sudo cp ona-service.deb local/ona/ona-service.deb

  $sudo cp ../isolinux/grub.cfg local/boot/grub/grub.cfg
  $sudo mkdir local/nocloud
  $sudo cp ../user-data/user-data.yml local/nocloud/user-data

  $sudo mkisofs -quiet -r -V "SWC Sensor Install CD" \
          -cache-inodes \
          -J -l -b boot/grub/i386-pc/eltorito.img \
          -joliet-long \
          -c boot.catalog -no-emul-boot \
          -boot-load-size 4 -boot-info-table \
          -eltorito-alt-boot -e boot/grub/x86_64-efi/efi_uga.mod -no-emul-boot \
          -o "../${ona_name}" local

  $sudo umount cdrom
  $sudo chown $USER:$USER "../${ona_name}"
  isohybrid "../${ona_name}"
# $sudo rm -rf "$DIR"/working
)

