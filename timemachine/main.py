#!/usr/bin/python3
"""
    Grateful Dead Time Machine -- copyright 2021 Steve Eichblatt

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
import logging
import optparse
import os

from timemachine import config, GD

parser = optparse.OptionParser()
parser.add_option(
    "--box", dest="box", type="string", default="v1", help="v0 box has screen at 270. [default %default]"
)
parser.add_option(
    "--dbpath", default=os.path.join(GD.ROOT_DIR, "metadata"), help="path to database [default %default]"
)
parser.add_option(
    "--test_update",
    action="store_true",
    default=False,
    help="test that software update succeeded[default %default]",
)
parser.add_option(
    "--pid_to_kill", type="int", default=None, help="process id to kill during test_update [default %default]"
)
parser.add_option(
    "-d",
    "--debug",
    type="int",
    default=0,
    help="If > 0, don't run the main script on loading [default %default]",
)
parser.add_option(
    "-v",
    "--verbose",
    action="store_true",
    default=False,
    help="Print more verbose information [default %default]",
)
parms, remainder = parser.parse_args()

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

if parms.debug > 0:
    logger.setLevel(logging.DEBUG)


try:
    config.load_options()
except Exception:
    logger.warning("Failed in loading options")
try:
    config.RELOAD_COLLECTIONS = "__reload__" in [x.lower() for x in config.optd["COLLECTIONS"]]
    config.UPDATE_COLLECTIONS = (
        "__update__" in [x.lower() for x in config.optd["COLLECTIONS"]]
    ) or config.optd["UPDATE_ARCHIVE_ON_STARTUP"]
    config.optd["COLLECTIONS"] = [x for x in config.optd["COLLECTIONS"] if not x.lower() in ["__reload__"]]
    optd = config.optd.copy()
    config.save_options(optd)
except Exception:
    logger.warning("Failed in saving options")
finally:
    # Although we allow __update__ to remain in the config file, we can't send it to the main program. Remove all __ collections here.
    config.optd["COLLECTIONS"] = [x for x in config.optd["COLLECTIONS"] if not x.startswith("__")]


def main_test_update():
    from timemachine import livemusic as tm

    parms.test_update = True
    tm.main_test_update(parms)


def main():
    # archive = Archivary.Archivary(parms.dbpath, reload_ids=reload_ids, with_latest=False, collection_list=config.optd['COLLECTIONS'])
    # player = GD.GDPlayer()
    if config.optd["MODULE"] == "livemusic":
        from timemachine import livemusic as tm
    elif config.optd["MODULE"] == "78rpm":
        from timemachine import m78rpm as tm
    else:
        logger.error(f"MODULE {config.optd['MODULE']} not in valid set of modules (['livemusic','78rpm'])")
        exit()

    tm.main(parms)
    exit()


"""
from timemachine import m78rpm
m78rpm.parms = parms
m78rpm.load_saved_state(m78rpm.state)
m78rpm.eloop.start()
"""

for k in parms.__dict__.keys():
    logger.info(f"{k:20s} : {parms.__dict__[k]}")

if __name__ == "__main__" and parms.debug == 0:
    main()

if __name__ == "__main__" and parms.test_update:
    main_test_update()
