#!/bin/bash

# Setup directories.
test_dir_name=deadstream_tmp
git_user=eichblatt
repo_name=deadstream.git
project_dir=$HOME/deadstream
test_dir=$HOME/$test_dir_name
backup_dir=$HOME/deadstream_previous.`cat /dev/random | tr -cd 'a-f0-9' | head -c 12`
log_file=$HOME/update.log

restore_services () {
   # put the old services back in place.
   echo "cd $project_dir/bin"
   cd $project_dir/bin
   echo "./services.sh"
   ./services.sh
   # Restart the services (Can i get the timemachine service to launch the serve_options?)
   echo "sudo service timemachine restart"
   sudo service timemachine restart
   echo "sudo service serve_options restart"
   sudo service serve_options restart
}

echo "Updating "
date

# Stop the running services
echo "sudo service timemachine stop"
sudo service timemachine stop
echo "sudo service serve_options stop"
sudo service serve_options stop

cd $project_dir
git_branch=`git branch | awk '/\*/ {print $2}'`
echo "git branch: $git_branch"
git remote update
new_code=`git status -uno | grep "fast-forward" | wc -l`
#new_code=`git checkout $git_branch | grep "behind" | wc -l`
if [ $new_code == 0 ]; then
   echo "No new code. Not updating "
   date
   restore_services
   exit 0
fi

# check if archive needs refreshing
update_archive=`find $project_dir/timemachine/metadata/ids.json -mtime +40 | wc -l`

# clone the repo into the test_dir
cd $HOME
rm -rf $test_dir
mkdir -p $test_dir
cd $HOME
echo "git clone https://github.com/$git_user/$repo_name $test_dir_name"
git clone https://github.com/$git_user/$repo_name $test_dir_name
echo "cd $test_dir"
cd $test_dir
echo "git remote set-url origin git@github.com:$git_user/$repo_name"
git remote set-url origin git@github.com:$git_user/$repo_name

echo "git checkout $git_branch"
git checkout $git_branch

pip3 install .

# If the archive has been refreshed in the last 40 days, copy it to the test dir
if [ $update_archive == 0 ]; then
   echo "cp -R $project_dir/timemachine/metadata $test_dir/timemachine/."
   cp -R $project_dir/timemachine/metadata $test_dir/timemachine/.
fi

# Set up the services. NOTE: Only for versions > 1 (because username was steve, not deadhead)
# NOTE: If there is something wrong with the service command, and it doesn't start we are screwed.
# So we are going to need factory reset command

cd $test_dir/bin
#version_1=`./board_version.sh | grep "^version 1$" | wc -l`
if [ $USER == deadhead ]; then
    echo "pwd is $PWD"
    ./services.sh
    stat=$?
    if [ $stat != 0 ]; then
       echo "status of services command: $stat"
       echo "rm -rf $test_dir"
       rm -rf $test_dir

       restore_services
       # exit with failure.
       exit $stat
    fi
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

restore_services

exit $stat
