#!/bin/bash

# Setup directories.
test_dir_name=deadstream_tmp
git_user=eichblatt
repo_name=deadstream.git
project_dir=$HOME/deadstream
test_dir=$HOME/$test_dir_name
backup_dir=$HOME/deadstream_previous.`cat /dev/random | tr -cd 'a-f0-9' | head -c 12`
log_file=$HOME/update.log

git_branch=`git branch | awk '/\*/ {print $2}'`
echo "git branch: $git_branch"
new_code=`git checkout $git_branch | grep "behind" | wc -l`
if [ $new_code == 0 ]; then
   echo "No new code. Not updating "
   date
   exit 0
fi

echo "Updating "
date

# Stop the running services
echo "sudo service timemachine stop"
sudo service timemachine stop
echo "sudo service serve_options stop"
sudo service serve_options stop

# check if archive needs refreshing
update_archive=`find $project_dir/timemachine/metadata/ids.json -mtime +40 | wc -l`

# clone the repo into the test_dir
cd $HOME
rm -rf $test_dir
mkdir -p $test_dir
cd $HOME
git clone https://github.com/$git_user/$repo_name $test_dir_name
mkdir -p $test_dir
cd $test_dir
git remote set-url origin git@github.com:$git_user/$repo_name

echo "git checkout $git_branch"
git checkout $git_branch

pip3 install .

# If the archive has been refreshed in the last 40 days, copy it to the test dir
if [ $update_archive == 0 ]; then
   echo "cp -R $project_dir/timemachine/metadata $test_dir/timemachine/."
   cp -R $project_dir/timemachine/metadata $test_dir/timemachine/.
fi

# Set up the services. NOTE: Could break things?
cd $test_dir/bin
echo "pwd is $PWD"
./services.sh
stat=$?
if [ $stat != 0 ]; then
   echo "status of services command: $stat"
   echo "rm -rf $test_dir"
   rm -rf $test_dir

   # put the old services back in place.
   echo "cd $project_dir/bin"
   cd $project_dir/bin
   echo "./services.sh"
   ./services.sh

   # exit with failure.
   exit $stat
fi

# Run the main program, make sure a button press and knob turn work.
python3 $test_dir/main.py --test_update
stat=$?
echo "status of test command: $stat"

# If this succeeds, put the new folder in place.
if [ $stat == 0 ]; then
   echo "mv $project_dir $backup_dir"
   mv $project_dir $backup_dir
   echo "mv $test_dir $project_dir"
   mv $test_dir $project_dir
fi

# Restart the services (Can i get the timemachine service to launch the serve_options?)
echo "sudo service timemachine restart"
sudo service timemachine restart
echo "sudo service serve_options restart"
sudo service serve_options restart

exit $stat
