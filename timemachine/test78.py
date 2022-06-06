import sys
import time
from threading import Event

from timemachine import Archivary
from timemachine import config
from timemachine import GD

track_event = Event()

#config.optd = {'COLLECTIONS': ['78rpm'], 'FAVORED_TAPER': 'miller', 'PLAY_LOSSLESS': 'false'}
config.optd = {'COLLECTIONS': ['georgeblood'], 'FAVORED_TAPER': 'miller', 'PLAY_LOSSLESS': 'false'}
aa = Archivary.Archivary(collection_list=config.optd['COLLECTIONS'])

print(F"tape dates on 1995-07-02 are {aa.tape_dates['1995-07-02']}")

""" example of choosing artists from 1941 """

def year_artists(year):
    id_dict = {}

    year_tapes = {k:v for k,v in aa.tape_dates.items() if k.startswith(f'{year}')}

    tapes = [item for sublist in year_tapes.values() for item in sublist]
    kvlist =  [(' '.join(x.identifier.split('_')[2].split('-')[:2]),x) for x in tapes]
    for kv in kvlist:
        id_dict.setdefault(kv[0],[]).append(kv[1])

    return id_dict


ya = year_artists(1943)  ## Have the year button display the ya.keys()
tape = ya['sister rosetta'][0]
p = GD.GDPlayer(tape)

p.play()
