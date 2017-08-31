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
#  - This is usually a very tempramental process, expect things to go
#    wrong.
#

RELEASE="${RELEASE:-16.04.2}"
ARCH="${ARCH:-amd64}"

UBUNTU="http://releases.ubuntu.com"

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
ubuntu_url="${url:-${UBUNTU}/${RELEASE}/${ubuntu_name}}"
suricata_url="https://s3.amazonaws.com/onstatic/suricata-service/master/suricata-service.deb"

shift $(($OPTIND-1))

if [ $(id -u) -eq "0" ] ; then
    sudo=""
else
    sudo="sudo"
fi

ret=$(which mkisofs)
if [ $ret -ne 0 ] ; then
  echo "missing mkisofs: $sudo apt-get install genisoimage"
  exit 1
fi

ret=$(which isohybrid)
if [ $ret -ne 0 ] ; then
  echo "missing isohybrid: $sudo apt-get install syslinux-utils"
  exit 1
fi


mkdir $DIR/working
pushd $DIR/working
  curl -L -o ${ubuntu_name} "${ubuntu_url}"
  curl -L -o suricata-service.deb "${suricata_url}"
  mkdir cdrom local
  $sudo mount -o loop "${ubuntu_name}" cdrom
  rsync -av cdrom/ local
  $sudo cp ../preseed/* local/preseed/
  $sudo cp -r ../ona local
  $sudo cp -r suricata-service.deb local/ona/suricata-service.deb
  $sudo cp ../isolinux/txt.cfg local/isolinux/txt.cfg
  $sudo mkisofs -r -V "Observable Networks Install CD" \
          -cache-inodes \
          -J -l -b isolinux/isolinux.bin \
          -c isolinux/boot.cat -no-emul-boot \
          -boot-load-size 4 -boot-info-table \
          -o "../${ona_name}" local
  $sudo umount cdrom
  $sudo chown $USER:$USER "../${ona_name}"
  isohybrid "../${ona_name}"
popd
$sudo rm -rf $DIR/working
