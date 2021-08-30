#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
version=v2
image_date=`date +%Y%m%d`
image_file=$SCRIPT_DIR/$version\_$image_date.img
media_folder=/media/steve

critical_command () {
   command=$1
   echo "$command"
   $command
   stat=$?
   echo "Status $stat"
   if [ $stat != 0 ]; then
      exit $stat
   fi
}

system () {
   command=$1
   echo "$command"
   $command
}


echo "Removing previous git folders"
system "cd $media_folder/rootfs/home/deadhead"
current_env=$(basename `readlink -f timemachine`)
files=`find . -maxdepth 1 -mindepth 1 -name env_\* -a -not -name $current_env -printf "%f "`
system "sudo rm -rf $files"
system "sudo rm -rf .knob_sense"
system "sudo rm -rf .ssh"


echo "Removing wpa_supplicant"
system "sudo rm $media_folder/rootfs/etc/wpa_supplicant/wpa_supplicant.conf*"

media_dirs="/dev/sdb1 /dev/sdb2"

for dir in $media_dirs; do
    system "sudo umount $dir"
done

system "sudo rm $image_file"
critical_command "sudo dd if=/dev/sdb of=$image_file bs=4M status=progress"

system "sudo pishrink.sh $image_file"

# NOTE: to burn an image use the command (or similar):
# sudo sh -c "pv v2_20210625.img > /dev/sdb"
# ./balenaEtcher-1.5.120-x64.AppImage > /dev/null 2>&1 &
