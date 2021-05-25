#!/bin/bash

sudo cp timemachine.service /etc/systemd/system/.
sudo cp connect_network.service /etc/systemd/system/.
sudo chmod 644 /etc/wpa_supplicant/wpa_supplicant.conf
sudo chown root /etc/wpa_supplicant/wpa_supplicant.conf
sudo chgrp root /etc/wpa_supplicant/wpa_supplicant.conf

sudo systemctl daemon-reload
sudo systemctl enable timemachine.service 
sudo systemctl enable connect_network.service
