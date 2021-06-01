#!/bin/bash

echo "Updating " > $HOME/update.log
date >> $HOME/update.log

cd $HOME/deadstream

git pull

sudo service timemachine restart
