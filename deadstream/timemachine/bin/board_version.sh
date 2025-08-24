#!/bin/bash

read lines words chars filename <<<$(cat /boot/config.txt | grep dtoverlay=gpio-shutdown | grep -v ^# | wc)

if [ "$lines" -eq "0" ]; then
   echo "version 1";
   exit 0
fi
echo "version 2"
