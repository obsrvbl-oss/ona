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

RELEASE="${RELEASE:-24.04.1}"
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
# Newly added
 ubuntu_name="ubuntu-${RELEASE}-live-server-${ARCH}.iso"
 ona_name="ona-${RELEASE}-server-${ARCH}.iso"
 ubuntu_url="${url:-$($DIR/build_iso_helper $RELEASE $VARIANT)}"

# ubuntu_name="ubuntu-24.04.1-live-server-amd64.iso"
# ona_name="ona-${RELEASE}-server-${ARCH}.iso"
ONA_URL="https://s3.amazonaws.com/onstatic/ona-service/master/"
if [ -n "$PUBLIC_ONA" ]; then
  ONA_URL="https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.2/"
fi
# netsa_pkg_name="netsa-pkg.deb"
ona_pkg_name="ona-service_UbuntuNoble_amd64.deb"

test -n "$ubuntu_url" || fatal "failed getting Ubuntu ISO download URL"

 ONA_URL="https://s3.amazonaws.com/onstatic/ona-service/master/"
 if [ -n "$PUBLIC_ONA" ]; then
   ONA_URL="https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.2/"

 fi

 #ona_service_url="${ONA_URL}ona-service_UbuntuNoble_amd64.deb"
 ona_service_url="https://assets-production.obsrvbl.com/ona-packages/obsrvbl-ona/v5.1.3/ona-service_UbuntuNoble_amd64.deb"
 netsa_pkg_url="https://assets-production.obsrvbl.com/ona-packages/netsa/v0.1.27/netsa-pkg.deb"



shift $(($OPTIND-1))

test $EUID -ne 0 && sudo="sudo"

[[ -d "$DIR" ]] || fatal  # invalid directory
[[ -d "$DIR"/working ]] || mkdir "$DIR"/working # working directory does not exist, so create it

major_version=$(echo "$RELEASE" | cut -d '.' -f 1)

# Check if the major version number is greater than 20
if [ "$major_version" -gt 20 ]; then
  which xorriso 1> /dev/null || fatal "missing xorriso: $sudo apt-get install xorriso -y"
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
  if [ ! -e "/root/$ubuntu_name" ]; then
    curl -L -o /root/${ubuntu_name} "${ubuntu_url}"
  fi

  cd "$DIR"/working
  #[[ -d "$DIR/local_files/" ]] && cp "$DIR"/local_files/* .
  curl -L -o netsa-pkg.deb "${netsa_pkg_url}"
  #curl -L -o "${ona_pkg_name}" "${ona_service_url}"
  $sudo cp /obsrvbl/images/iso/ona-service_UbuntuNoble_amd64.deb /obsrvbl/images/iso/working/





$sudo apt-get -y update
# you can install packages here if you want

PACKAGES="apt-transport-https iptables-persistent ipset libjansson4 libltdl7 liblzo2-2 libnet1 libyaml-0-2 nano ntp ntpdate snmp tcpdump net-tools libsnappy1v5 python3-dateutil"
$sudo apt-get -yyqq install --download-only ${PACKAGES}




  # local is root dir in ISO
  mkdir cdrom local
  pwd

  $sudo mount -o loop --read-only "/root/${ubuntu_name}" cdrom
  rsync -av --quiet cdrom/ local

  $sudo cp -r /var/cache/apt local
  $sudo cp -r ../ona local
  $sudo cp netsa-pkg.deb local/ona/netsa-pkg.deb
  $sudo cp ${ona_pkg_name} local/ona/${ona_pkg_name}

  echo "New format: $NEW_FORMAT "
  if [ -n "$NEW_FORMAT" ]; then
    # copy autoinstall folders for grub
    $sudo cp -r ../autoinstall/nocloud-dhcp  local/
    $sudo cp ../isolinux/grub.cfg local/boot/grub/grub.cfg
  else
    $sudo cp ../preseed/* local/preseed/
    $sudo cp ../isolinux/txt.cfg local/isolinux/txt.cfg
    $sudo cp ../isolinux/grub.cfg local/boot/grub/grub.cfg
  fi

  if [ -n "$NEW_FORMAT" ]; then
    xorriso -as mkisofs -r  -V 'SWC Sensor Install CD' \
      -o "../${ona_name}"\
      --grub2-mbr --interval:local_fs:0s-15s:zero_mbrpt,zero_gpt:"/root/${ubuntu_name}" \
      -partition_offset 16 \
      --mbr-force-bootable \
      -append_partition 2 0xef \
      --interval:local_fs:4099440d-4109507d::"/root/${ubuntu_name}" \
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

