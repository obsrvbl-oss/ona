#!/bin/bash -ex

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

RELEASE="${RELEASE:-18.04.4}"
ARCH="${ARCH:-amd64}"

UBUNTU="http://cdimage.ubuntu.com/ubuntu/releases"

DIR=$(cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd)

while getopts "f:a:r:" opt ; do
    case $opt in
        f) url="file://$(readlink -f $OPTARG)"
           ;;
        a) ARCH="$OPTARG"
           ;;
        r) RELEASE="$OPTARG"
           ;;
        ?) echo "invalid argument"
           ;;
    esac
done

ubuntu_name="ubuntu-${RELEASE}-server-${ARCH}.iso"
ona_name="ona-${RELEASE}-server-${ARCH}.iso"
ubuntu_url="${url:-${UBUNTU}/${RELEASE}/release/${ubuntu_name}}"
ona_service_url="https://s3.amazonaws.com/onstatic/ona/master/ona-service_UbuntuXenial_amd64.deb"
netsa_pkg_url="https://onstatic.s3.amazonaws.com/netsa-pkg.deb"

shift $(($OPTIND-1))

test $EUID -ne 0 && sudo="sudo"
which mkisofs || (echo "missing mkisofs: $sudo apt-get install genisoimage" && false)
which isohybrid || (echo "missing isohybrid: $sudo apt-get install syslinux-utils" && false)

mkdir "$DIR"/working
test -f ${ubuntu_name} && cp ${ubuntu_name} working && echo "using local ${ubuntu_name}" || echo "downloading ${ubuntu_name}"
pushd "$DIR"/working
  test -f ${ubuntu_name} || curl -L -o ${ubuntu_name} "${ubuntu_url}"
  curl -L -o netsa-pkg.deb "${netsa_pkg_url}"
  curl -L -o ona-service.deb "${ona_service_url}"
  mkdir cdrom local
  $sudo mount -o loop "${ubuntu_name}" cdrom
  rsync -av --quiet cdrom/ local
  $sudo cp ../preseed/* local/preseed/
  $sudo cp -r ../ona local
  $sudo cp -r netsa-pkg.deb local/ona/netsa-pkg.deb
  $sudo cp -r ona-service.deb local/ona/ona-service.deb
  $sudo cp ../isolinux/txt.cfg local/isolinux/txt.cfg
  $sudo cp ../isolinux/grub.cfg local/boot/grub/grub.cfg
  $sudo mkisofs -quiet -r -V "SWC Sensor Install CD" \
          -cache-inodes \
          -J -l -b isolinux/isolinux.bin \
          -c isolinux/boot.cat -no-emul-boot \
          -boot-load-size 4 -boot-info-table \
          -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
          -o "../${ona_name}" local
  $sudo umount cdrom
  $sudo chown $USER:$USER "../${ona_name}"
  isohybrid "../${ona_name}"
popd
$sudo rm -rf "$DIR"/working
