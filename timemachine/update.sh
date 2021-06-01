#!/bin/bash

echo "Updating " > $HOME/update.log
date >> $HOME/update.log

cd $HOME/deadstream

git pull >> $HOME/update.log

sudo service timemachine restart
