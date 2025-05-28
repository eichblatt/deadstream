#! /bin/bash

collections="Phish"

help()
{
    echo "Syntax: update_cloud_meta.sh [-c collections | -n | -h]"
}

while getopts "hc:n" option; do 
    case $option in 
        h) help; exit;;
        c) collections=${OPTARG};;
        n) skip_authenticate=0;;
        \?) echo "Error, invalid option";exit;;
    esac
done

echo "source $HOME/projects/cld_srv/cloudenv/bin/activate"
source $HOME/projects/cld_srv/cloudenv/bin/activate

if [ -z $skip_authenticate ]; then
    echo "gcloud auth application-default login"
    gcloud auth application-default login
fi

echo "ipython update_cloud_meta.py -- --collections $collections"
ipython update_cloud_meta.py -- --collections $collections