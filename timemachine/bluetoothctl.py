# Based on ReachView code from Egor Fedorov (egor.fedorov@emlid.com)
# Updated for Python 3.6.8 on a Raspberry  Pi
# source: https://gist.github.com/castis/0b7a162995d0b465ba9c84728e60ec01#file-bluetoothctl-py 

# If you are interested in using ReachView code as a part of a
# closed source project, please contact Emlid Limited (info@emlid.com).

# This file is part of ReachView.

# ReachView is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ReachView is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ReachView.  If not, see <http://www.gnu.org/licenses/>.

import time
import pexpect
import re
import subprocess
import sys
import logging


logger = logging.getLogger("btctl")

def escape_ansi(line):
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    if isinstance(line,list):
        return [ansi_escape.sub('', l) for l in line]
    return ansi_escape.sub('', line)

class Bluetoothctl:
    """A wrapper for bluetoothctl utility."""

    def __init__(self):
        subprocess.check_output("sudo rfkill unblock bluetooth", shell=True)
        self.process = pexpect.spawnu("bluetoothctl", echo=False)
        self.process.expect("Agent registered")
        self.terminator = "#"
        #p = self.get_prompt()
        # self.terminator = escape_ansi(self.process.before)
        #self.terminator = self.get_connected_device_name()

    def send(self, command, pause=0):
        self.process.send(f"{command}\n")
        time.sleep(pause)
        if self.process.expect([self.terminator, pexpect.EOF, pexpect.TIMEOUT]):
            raise Exception(f"failed after {command}")

    def get_output(self, *args, **kwargs):
        """Run a command in bluetoothctl prompt, return output as a list of lines."""
        self.send(*args, **kwargs)
        return self.process.before.split("\r\n")

    def start_scan(self):
        """Start bluetooth scanning process."""
        try:
            self.send("scan on")
        except Exception as e:
            logger.error(e)

    def stop_scan(self):
        """Start bluetooth scanning process."""
        try:
            self.send("scan off")
        except Exception as e:
            logger.error(e)

    def scan(self, timeout=5):
        """Start and stop bluetooth scanning process."""
        self.start_scan()
        time.sleep(timeout)
        self.stop_scan()

    def get_prompt(self):
        """Read the bluetoothctl prompt, which is the name of device if connected"""
        prompt = self.get_output("")   # send an empty line
        return prompt

    def get_connected_device_name(self):
        """Read the name of the device from the bluetoothctl prompt """
        device_name = ""
        prompt = self.get_prompt()
        if len(prompt) < 1:
            return device_name
        device_string = escape_ansi(prompt[0])
        s = re.search(r'\[(.*)\]',device_string)
        if s:
            device_name = s.group(1)
        return device_name

    def make_discoverable(self):
        """Make device discoverable."""
        try:
            self.send("discoverable on")
        except Exception as e:
            logger.error(e)

    def parse_device_info(self, info_string):
        """Parse a string corresponding to a device."""
        device = {}
        block_list = ["[\x1b[0;", "removed"]
        if not any(keyword in info_string for keyword in block_list):
            try:
                device_position = info_string.index("Device")
            except ValueError:
                pass
            else:
                if device_position > -1:
                    attribute_list = info_string[device_position:].split(" ", 2)
                    device = {
                        "mac_address": attribute_list[1],
                        "name": attribute_list[2],
                    }
        return device

    def get_available_devices(self):
        """Return a list of tuples of paired and discoverable devices."""
        available_devices = []
        try:
            out = self.get_output("devices")
        except Exception as e:
            logger.error(e)
        else:
            for line in out:
                device = self.parse_device_info(line)
                if device:
                    available_devices.append(device)
        return available_devices

    def get_paired_devices(self):
        """Return a list of tuples of paired devices."""
        paired_devices = []
        try:
            out = self.get_output("paired-devices")
        except Exception as e:
            logger.error(e)
        else:
            for line in out:
                device = self.parse_device_info(line)
                if device:
                    paired_devices.append(device)
        return paired_devices

    def get_discoverable_devices(self):
        """Filter paired devices out of available."""
        available = self.get_available_devices()
        paired = self.get_paired_devices()
        return [d for d in available if d not in paired]

    def is_candidate(self, device):
        """Filter interesting devices out of available."""
        mac_address = device['mac_address']
        dash_address = mac_address.replace(':','-')
        name = device['name']
        if name == dash_address or name.startswith('RSSI') or name.startswith('TxPower'):
            return False
        return True

    def get_candidate_devices(self):
        candidate_devices = []
        try:
            dd = self.get_discoverable_devices()
            ad = self.get_available_devices()
            unique_devices = list({v['mac_address']:v for v in dd+ad}.values())
            candidate_devices = [d for d in unique_devices if self.is_candidate(d)]
        except Exception as e:
            logger.error(e)
        return candidate_devices

    def get_device_info(self, mac_address):
        """Get device info by mac address."""
        try:
            out = self.get_output(f"info {mac_address}")
        except Exception as e:
            logger.error(e)
            return False
        else:
            return out

    def pair(self, mac_address):
        """Try to pair with a device by mac address."""
        try:
            self.send(f"pair {mac_address}", 4)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["Failed to pair", "Pairing successful", pexpect.EOF]
            )
            return res == 1

    def trust(self, mac_address):
        try:
            output = self.get_output(f"trust {mac_address}")
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                [".*not available\r\n", "trust succe", pexpect.EOF]
            )
            return res == 1

    def remove(self, mac_address):
        """Remove paired device by mac address, return success of the operation."""
        try:
            self.send(f"remove {mac_address}", 3)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["not available", "Device has been removed", pexpect.EOF]
            )
            return res == 1

    def connect(self, mac_address):
        """Try to connect to a device by mac address."""
        try:
            self.send(f"connect {mac_address}", 2)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["Failed to connect", "Connection successful", pexpect.EOF]
            )
            return res == 1

    def disconnect(self, mac_address):
        """Try to disconnect to a device by mac address."""
        try:
            self.send(f"disconnect {mac_address}", 2)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["Failed to disconnect", "Successful disconnected", pexpect.EOF]
            )
            return res == 1
