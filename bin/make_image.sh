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
system "sudo rm -rf $media_folder/rootfs/home/deadhead/deadstream_prev*"

echo "Removing wpa_supplicant"
system "sudo rm $media_folder/rootfs/etc/wpa_supplicant/wpa_supplicant.conf*"

media_dirs="/dev/sdb1 /dev/sdb2"

for dir in $media_dirs; do
    system "sudo umount $dir"
done

system "sudo rm $image_file"
critical_command "sudo dd if=/dev/sdb of=$image_file bs=4M status=progress"

system "sudo pishrink.sh $image_file"
