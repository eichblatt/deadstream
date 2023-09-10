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

def get_os_info(field="VERSION_ID"):
    retval = None
    try:
        cmd = "cat /etc/os-release"
        lines = subprocess.check_output(cmd, shell=True)
        lines = lines.decode().split("\n")
        for line in lines:
            split_line = line.split("=")
            if split_line[0] == field:
                retval = split_line[1].strip('"')
                return retval
    except Exception as e:
        logger.warning(f"Failed to get OS info {e}")
        return retval

def get_os_version():
    global OS_VERSION  # cache the value of os version
    if OS_VERSION is None:
        try:
            OS_VERSION = float(get_os_info("VERSION_ID"))
        except:
            pass
    return OS_VERSION

def get_os_name():
    os_name = "UNKNOWN"
    try:
        os_name = get_os_info("NAME")
    except:
        pass
    return os_name

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

def get_board_version():
    if get_os_name() == "Ubuntu":
        return 1
    try:
        cmd = "board_version.sh"
        raw = subprocess.check_output(cmd, shell=True)
        raw = raw.decode()
        if raw == "version 2\n":
            return 2
    except Exception:
        return 1



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
        

def usb_mounted(archive_dir):
    logger.info("Checking USB Mounted")

    if get_os_name() == "Ubuntu":  # in this case, look for archive in filesystem
        return is_writable(archive_dir)

    # Make sure that the archive_dir points to the USB archive.
    if os.path.islink(archive_dir):
        os.unlink(archive_dir)
        os.symlink("/mnt/usb/archive",archive_dir)

    partitions = psutil.disk_partitions()
    try:
        for p in partitions:
            if (p.mountpoint == "/mnt/usb") & is_writable(archive_dir):
                return True
    except Exception:
        return False

    return False

def mount_local_archive(archive_dir):
    if usb_mounted(archive_dir):
        return 
    cmd = "sudo mount -ouser,umask=000 /dev/sda1 /mnt/usb"
    logger.info(f"cmd is {cmd}")
    try:
        os.system(cmd)
        os.symlink("/mnt/usb/archive",archive_dir)
    except Exception:
        pass
    



def get_local_mode():
    # Return the "local_mode". Modes are:
    # 0 -- no local archive
    # 1 -- local archive exists and is playable
    # 2 -- local archive playable, and some local COLLECTIONS selected
    # 3 -- local archive selected, and no internet connectivity
    # 
    local_mode = 0
    options_file = os.path.join(os.getenv("HOME"),".timemachine_options.txt")
    archive_dir = os.path.join(os.getenv("HOME"),"archive")
    try:
        mount_local_archive(archive_dir)
    except Exception as e:
        logger.warning(f"Failed to mount local archive {e}")
    try:
        if usb_mounted(archive_dir):
            local_mode = 1
        if local_mode > 0:  # Are there any Local_ collections?
            config.load_options()
            opts_dict = config.optd
            for coll in opts_dict["COLLECTIONS"].split(","):
                if "Local_" in coll:
                    local_mode = 2
        if local_mode == 2:  # Are we disconnected from wifi?
            if get_ip() is None:
                local_mode = 3
        logger.info(f"Local mode is set to {local_mode}")
        return local_mode
    except Exception:
        logger.warning(f"Failed to get local mode. {local_mode} -")
        return local_mode
