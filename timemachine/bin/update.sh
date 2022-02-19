#!/bin/bash

# Print some setup variables
echo "home is $HOME"
echo "Updating "
date

python_version=`python3 -c 'import sys; v = sys.version_info; print(f"{v[0]}.{v[1]}")'`
old_env=$HOME/timemachine
timemachine_path=lib/python$python_version/site-packages/timemachine
TIMEMACHINE=$old_env/$timemachine_path
echo "TIMEMACHINE var is $TIMEMACHINE"
current_metadata_path=$TIMEMACHINE/metadata

# define local functions
system () {
   command=$1
   echo "$command"
   $command
}

restore_services () {
   # put the old services back in place.
   echo "services.sh"
   services.sh
   # Restart the services (Can i get the timemachine service to launch the serve_options?)
   echo "sudo service timemachine restart"
   sudo service timemachine restart
   echo "sudo service serve_options restart"
   sudo service serve_options restart
   echo "sudo service pulseaudio restart"
   sudo service pulseaudio restart
}

cleanup_old_envs () {
   echo "Cleaning up old envs ... "
   system "cd $HOME"
   echo "current_env=$(basename `readlink -f timemachine`)"
   current_env=$(basename `readlink -f timemachine`)
   echo "files=`find . -maxdepth 1 -mindepth 1 -name env_\* -a -not -name $current_env -printf '%f '`"
   files=`find . -maxdepth 1 -mindepth 1 -name env_\* -a -not -name $current_env -printf "%f "`
   echo "files are $files"
   files2delete=`ls -1trd $files | head -n -8`
   echo "files2delete are $files2delete"
   files2delete=`ls -1trd $files | head -n -8 | xargs -d '\n' rm -rf --`
   echo "Done cleaning up old envs"
}

# get the tag, to check if an update is required
git_branch=main    # Make this a command-line option!
if [ -f $TIMEMACHINE/.latest_tag ]; then
    local_tag=`cat $TIMEMACHINE/.latest_tag | cut -f1 -d"-"`
else
    local_tag="v0.4.1"
fi
remote_tag=`git -c 'versionsort.suffix=-' ls-remote --tags --sort='v:refname' https://github.com/eichblatt/deadstream.git | grep -v \{\} | tail --lines=1 | cut --delimiter='/' --fields=3`

git_branch=$remote_tag

if [[ $HOSTNAME == deadstream* ]]; then
   git_branch=dev
else
   system "sudo systemctl disable ssh"
fi


# Perform shell tasks which may require 2 updates to take effect
[ ! -f $HOME/.phishinkey ] && echo '8003bcd8c378844cfb69aad8b0981309f289e232fb417df560f7192edd295f1d49226ef6883902e59b465991d0869c77' > $HOME/.phishinkey

echo "yes | sudo apt-get install pulseaudio" 
yes | sudo apt-get install pulseaudio 

sudo grep -qF -- "enable_uart=1" /boot/config.txt || echo "enable_uart=1" | sudo tee -a /boot/config.txt
sudo grep -q -- "^default-server = /var/run/pulse/native" /etc/pulse/client.conf || echo "default-server = /var/run/pulse/native" | sudo tee -a /etc/pulse/client.conf
sudo grep -q -- "^autospawn = no" /etc/pulse/client.conf || echo "autospawn = no" | sudo tee -a /etc/pulse/client.conf
sudo usermod -a -G audio,video,bluetooth,spi,gpio,pulse,pulse-access deadhead
sudo usermod -a -G audio,bluetooth pulse
sudo usermod -a -G pulse,pulse-access root
sudo usermod -a -G pulse bluetooth

# If no update is required, then exit.
echo "git branch is $git_branch"
if [ "$local_tag" = "$git_branch" ]; then
   echo "Local repository up to date. Not updating"
   exit 0
fi


# Stop the timemachine service.
system "sudo service timemachine stop"

# Start the music
echo "[ ! -f $HOME/helpontheway.ogg ] && wget -O $HOME/helpontheway.ogg https://archive.org/download/gd75-08-13.fm.vernon.23661.sbeok.shnf/gd75-08-13d1t02.ogg "
[ ! -f $HOME/helpontheway.ogg ] && wget -O $HOME/helpontheway.ogg https://archive.org/download/gd75-08-13.fm.vernon.23661.sbeok.shnf/gd75-08-13d1t02.ogg
echo "mpv --volume=60 --really-quiet $HOME/helpontheway.ogg $HOME/helpontheway.ogg $HOME/helpontheway.ogg &"
mpv --volume=60 --really-quiet $HOME/helpontheway.ogg $HOME/helpontheway.ogg $HOME/helpontheway.ogg &
help_on_the_way_pid=$!


# Perform the update
system "cd $HOME"
env_name=env_`date +%Y%m%d`.`cat /dev/random | tr -cd 'a-f0-9' | head -c 8`
system "python3 -m venv $env_name"
system "source $env_name/bin/activate"
system "pip3 install wheel"
system "pip3 install git+https://github.com/eichblatt/deadstream.git@$git_branch"

new_metadata_path=$HOME/$env_name/$timemachine_path/metadata

# Copy the metadata
echo "checking for metadata to copy"
if [ -d $current_metadata_path/GratefulDead_ids ]; then
   echo "cp -pR $current_metadata_path/*_ids $new_metadata_path/."
   cp -pR $current_metadata_path/*_ids $new_metadata_path/.
fi

# Stop the running services
system "sudo service timemachine stop"
system "sudo service serve_options stop"

# Test the update
system "timemachine_test_update --test_update 1 --pid_to_kill $help_on_the_way_pid"
stat=$?
echo "status of test command: $stat"
kill $help_on_the_way_pid

# Put the update in place, if it was successful.
system "cd $HOME" # NOTE: we should already be here.
if [ $stat == 0 ]; then
   system "ln -sfn $env_name timemachine"
   echo "echo $remote_tag > $env_name/$timemachine_path/.latest_tag"
   sudo echo $remote_tag > $env_name/$timemachine_path/.latest_tag
else
   system "rm -rf $env_name"
fi

restore_services
cleanup_old_envs

exit $stat
