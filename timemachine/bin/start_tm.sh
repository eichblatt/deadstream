#!/bin/bash

# Print some setup variables
echo "home is $HOME"
echo "Updating "
date
export PATH=$PATH:/home/deadhead/.local/bin

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

check_connected () {
   status=`systemctl status connect_network | grep Active`
   echo $status | grep -q "exited"
   return $?
}

until check_connected; do  
	if [ $? -eq 1 ]; then 
		echo "sleeping 5"
		sleep 5; 
	else 
		echo "sleeping 2"
		sleep 2; 
	fi 
done

echo "done, apparently network is connected"
# source /home/deadhead/timemachine/bin/activate && timemachine
/home/deadhead/.local/bin/timemachine
