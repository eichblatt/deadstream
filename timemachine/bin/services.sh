#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")

echo "running $SCRIPT_NAME"
echo "Copying service scripts from $SCRIPT_DIR to /etc/systemd/system"
sudo cp $SCRIPT_DIR/timemachine.service /etc/systemd/system/.
sudo cp $SCRIPT_DIR/connect_network.service /etc/systemd/system/.
sudo cp $SCRIPT_DIR/serve_options.service /etc/systemd/system/.
sudo cp $SCRIPT_DIR/update.service /etc/systemd/system/.
sudo cp $SCRIPT_DIR/calibrate.service /etc/systemd/system/.
sudo cp $SCRIPT_DIR/pulseaudio.service /etc/systemd/system/.

echo "changing permissions on wpa_supplicant"
sudo chmod 644 /etc/wpa_supplicant/wpa_supplicant.conf
sudo chown root /etc/wpa_supplicant/wpa_supplicant.conf
sudo chgrp root /etc/wpa_supplicant/wpa_supplicant.conf

echo "reenabling services"
sudo systemctl daemon-reload
sudo systemctl enable calibrate.service
sudo systemctl enable connect_network.service
sudo systemctl enable timemachine.service
sudo systemctl enable serve_options.service
sudo systemctl disable update.service
sudo systemctl enable pulseaudio.service

echo "finished $SCRIPT_NAME"
exit 0
