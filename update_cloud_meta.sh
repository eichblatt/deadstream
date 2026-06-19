#! /bin/bash

collections="existing"   #"Phish"
skip_authenticate=1  # Skip authentication by default

help()
{
    echo "Syntax: update_cloud_meta.sh [-c collections | -a | -h]"
}

while getopts "hc:a" option; do 
    case $option in 
        h) help; exit;;
        c) collections=${OPTARG};;
        a) skip_authenticate=0;;
        \?) echo "Error, invalid option";exit;;
    esac
done

CONDA_PATH="$HOME/miniconda3/bin/conda" 
# Check if conda environment 'myenv' is active
if [[ "${CONDA_DEFAULT_ENV}" != "myenv" ]]; then
    # Initialize conda for bash shell
    echo "Activating myenv conda environment"
    # source "$(conda info --base)/etc/profile.d/conda.sh"
    source "$(dirname $CONDA_PATH)/../etc/profile.d/conda.sh"
    conda activate myenv
    if [[ "${CONDA_DEFAULT_ENV}" != "myenv" ]]; then
        echo "Failed to activate 'myenv' conda environment"
        exit 1
    fi
fi

echo "source $HOME/projects/cld_srv/cloudenv/bin/activate"
source $HOME/projects/cld_srv/cloudenv/bin/activate

if [ -z $skip_authenticate ]; then
    echo "gcloud auth application-default login"
    gcloud auth application-default login
fi

echo "ipython update_cloud_meta.py -- --collections $collections"
ipython update_cloud_meta.py -- --collections $collections