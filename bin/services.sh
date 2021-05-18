#!/bin/bash

sudo cp timemachine.service /etc/systemd/system/.
sudo cp connect_network.service /etc/systemd/system/.

sudo systemctl daemon-reload
sudo systemctl enable timemachine.service 
sudo systemctl enable connect_network.service
