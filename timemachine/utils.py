#!/usr/bin/python3
"""
    Live Music Time Machine -- copyright 2021, 2023 spertilo.net

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import json
import logging
import os
import psutil
import re
import subprocess

import pkg_resources

from timemachine import config

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)
VERBOSE = 5
logging.addLevelName(VERBOSE, "VERBOSE")
logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

OS_VERSION = None

def get_os_version():
    global OS_VERSION  # cache the value of os version
    if OS_VERSION is None:
        try:
            cmd = "cat /etc/os-release"
            lines = subprocess.check_output(cmd, shell=True)
            lines = lines.decode().split("\n")
            for line in lines:
                split_line = line.split("=")
                if split_line[0] == "VERSION_ID":
                    OS_VERSION = int(split_line[1].strip('"'))
        except Exception:
            logger.warning("Failed to get OS Version")
    return OS_VERSION


def get_version():
    __version__ = "v1.0"
    try:
        latest_tag_path = pkg_resources.resource_filename("timemachine", ".latest_tag")
        with open(latest_tag_path, "r") as tag:
            __version__ = tag.readline()
        __version__ = __version__.strip()
        return __version__
    except Exception as e:
        logging.warning(f"get_version error {e}")
    finally:
        return __version__

def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(" ")[0]
    if not re.match(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", ip):
        ip = None
    return ip

def is_writable(path):
    try:
        return os.access(path, os.W_OK)
    except FileNotFoundError:
        return False


def get_local_mode():
    # Return the "local_mode". Modes are:
    # 0 -- no local archive
    # 1 -- local archive exists and is playable
    # 2 -- local archive playable, and some local COLLECTIONS selected
    # 3 -- local archive selected, and no internet connectivity
    # 
    local_mode = 0
    archive_dir = os.path.join(os.getenv("HOME"),"archive")
    options_file = os.path.join(os.getenv("HOME"),".timemachine_options.txt")
    partitions = psutil.disk_partitions()
    try:
        for p in partitions:
            if (p.mountpoint == "/mnt/usb") & is_writable(archive_dir):
                local_mode = 1
                break 
        if local_mode > 0:  # Are there any Local_ collections?
            opts_dict = json.load(open(options_file,'r'))
            for coll in opts_dict["COLLECTIONS"].split(","):
                if "Local_" in coll:
                    local_mode = 2
        if local_mode == 2:  # Are we disconnected from wifi?
            if get_ip() is None:
                local_mode = 3
    except Exception:
        return local_mode
