import os
import time
from threading import Event

from timemachine import Archivary
from timemachine import config
from timemachine import GD

track_event = Event()

config.load_options()


gd = Archivary.GDArchive(collection_list=["DeadAndCompany"])
tape_dates = gd.tape_dates
