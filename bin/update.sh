#!/bin/bash

project_dir=$HOME/deadstream
test_dir=$HOME/deadstream_tmp
backup_dir=$HOME/deadstream_previous.`cat /dev/random | tr -cd 'a-f0-9' | head -c 12`
log_file=$HOME/update.log

echo "Updating "
date

echo "sudo service timemachine stop"
sudo service timemachine stop
echo "sudo service serve_options stop"
sudo service serve_options stop

rm -rf $test_dir
mkdir -p $test_dir
cd $HOME
git clone https://github.com/eichblatt/deadstream.git deadstream_tmp
mkdir -p $test_dir
cd $test_dir
echo "git checkout dev"
git checkout dev
pip3 install .

cd $test_dir/bin
echo "pwd is $PWD"
./services.sh
stat=$?
if [ $stat != 0 ]; then
   echo "status of services command: $stat"
   echo "rm -rf $test_dir"
   rm -rf $test_dir
   exit $stat
fi

python3 $test_dir/main.py --test_update
stat=$?
echo "status of test command: $stat"

if [ $stat == 0 ]; then
   echo "mv $project_dir $backup_dir"
   mv $project_dir $backup_dir
   echo "mv $test_dir $project_dir"
   mv $test_dir $project_dir
fi

echo "sudo service timemachine restart"
sudo service timemachine restart
echo "sudo service serve_options restart"
sudo service serve_options restart

exit $stat
