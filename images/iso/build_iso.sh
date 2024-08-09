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

ONA_URL="https://s3.amazonaws.com/onstatic/ona-service/master/"
if [ -n "$PUBLIC_ONA" ]; then
  ONA_URL="https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.2/"
fi

ona_service_url="https://s3.amazonaws.com/onstatic/ona-service/master/ona-service_UbuntuXenial_amd64.deb"
netsa_pkg_url="https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb"

shift $(($OPTIND-1))

test $EUID -ne 0 && sudo="sudo"


[[ -d "$DIR" ]] || fatal  # invalid directory
[[ -d "$DIR"/working ]] || mkdir "$DIR"/working # working directory does not exist, so create it

major_version=$(echo "$RELEASE" | cut -d '.' -f 1)
# Check if the major version number is greater than 20
if [ "$major_version" -gt 20 ]; then
  which mkisofs 1> /dev/null || fatal "missing xorriso: $sudo apt-get install xorriso -y"
  NEW_FORMAT=true
  BOOT_CAT="/boot.catalog"
  EFI='/boot/grub/i386-pc/eltorito.img'
  ELTORITO='/boot/grub/i386-pc/eltorito.img'

else
  which mkisofs 1> /dev/null || fatal "missing mkisofs: $sudo apt-get install genisoimage"
  which isohybrid 1> /dev/null || fatal "missing isohybrid: $sudo apt-get install syslinux-utils"
  BOOT_CAT="isolinux/boot.cat"
  EFI="isolinux/isolinux.bin"
  ELTORITO="boot/grub/efi.img"
fi


(
  set -e
  if [ ! -e "$ubuntu_name" ]; then
    curl -L -o ${ubuntu_name} "${ubuntu_url}"
  fi
  cd "$DIR"/working
  curl -L -o netsa-pkg.deb "${netsa_pkg_url}"
  curl -L -o ona-service.deb "${ona_service_url}"
  # local is root dir in ISO
  mkdir cdrom local
  $sudo mount -o loop --read-only "../${ubuntu_name}" cdrom
  rsync -av --quiet cdrom/ local
  $sudo cp -r ../ona local
  $sudo cp netsa-pkg.deb local/ona/netsa-pkg.deb
  $sudo cp ona-service.deb local/ona/ona-service.deb

  echo "new format: $NEW_FORMAT "
  if [ -n "$NEW_FORMAT" ]; then
    # copy autoinstall folders for grub
    $sudo cp -r ../autoinstall/* local/
    $sudo cp ../isolinux/grub-new-format.cfg local/boot/grub/grub.cfg
  else
    $sudo cp ../preseed/* local/preseed/
    $sudo cp ../isolinux/txt.cfg local/isolinux/txt.cfg
    $sudo cp ../isolinux/grub.cfg local/boot/grub/grub.cfg
  fi

  if [ -n "$NEW_FORMAT" ]; then
    xorriso -as mkisofs -r  -V 'SWC Sensor Install CD' \
      -o "../${ona_name}"\
      --grub2-mbr --interval:local_fs:0s-15s:zero_mbrpt,zero_gpt:"../${ubuntu_name}" \
      -partition_offset 16 \
      --mbr-force-bootable \
      -append_partition 2 0xef \
      --interval:local_fs:4099440d-4109507d::"../${ubuntu_name}" \
      -appended_part_as_gpt \
      -c "${BOOT_CAT}" \
      -b "${ELTORITO}" \
      -no-emul-boot -boot-load-size 4 -boot-info-table \
      --grub2-boot-info \
      -eltorito-alt-boot \
      -e '--interval:appended_partition_2:::' \
      -no-emul-boot \
      local
  else
    $sudo mkisofs -quiet -r -V "SWC Sensor Install CD" \
      -cache-inodes \
      -J -l -b "${BOOT_CAT}" \
      -c "${EFI}" -no-emul-boot \
      -joliet-long \
      -boot-load-size 4 -boot-info-table \
      -eltorito-alt-boot -e "${ELTORITO}" -no-emul-boot \
      -o "../${ona_name}" local

    isohybrid "../${ona_name}"
  fi

  $sudo umount cdrom
  $sudo chown $USER:$USER "../${ona_name}"
  $sudo rm -rf "$DIR"/working
)
