import os
import time
from threading import Event

from timemachine import Archivary
from timemachine import config
from timemachine import GD

track_event = Event()

config.load_options()


def test_format_notitles():
    laa = Archivary.Archivary(collection_list=["Local_BobDylan"])
    la = laa.archives[0]
    tape = la.tape_dates["1997-11-02"][0]  # no numbers, clause 4
    os.system(f"rm {tape.meta_path}")
    tracks = tape.tracks()
    assert tracks[9].title == "Audio Track"


def test_format_6():
    laa = Archivary.Archivary(collection_list=["Local_BobDylan"])
    la = laa.archives[0]
    tape = la.tape_dates["2000-07-22"][0]  # no numbers, clause 4
    os.system(f"rm {tape.meta_path}")
    tracks = tape.tracks()
    assert tracks[9].title == "Tears of Rage"


def test_format_5():
    laa = Archivary.Archivary(collection_list=["Local_BobDylan"])
    la = laa.archives[0]
    tape = la.tape_dates["1988-10-19"][0]
    os.system(f"rm {tape.meta_path}")
    tracks = tape.tracks()
    assert tracks[2].title == "John Brown"


def test_format_4():
    laa = Archivary.Archivary(collection_list=["Local_BobDylan"])
    la = laa.archives[0]
    tape = la.tape_dates["1988-10-16"][0]
    os.system(f"rm {tape.meta_path}")
    tracks = tape.tracks()
    assert tracks[11].title == "In The Garden"


def test_format_3():
    laa = Archivary.Archivary(collection_list=["Local_BobDylan"])
    la = laa.archives[0]
    tape = la.tape_dates["1974-01-31"][0]
    os.system(f"rm {tape.meta_path}")
    tracks = tape.tracks()
    assert tracks[21].title == "Set Break"


def test_format_2():
    laa = Archivary.Archivary(collection_list=["Local_BobDylan"])
    la = laa.archives[0]
    tape = la.tape_dates["2006-04-03"][0]
    os.system(f"rm {tape.meta_path}")
    tracks = tape.tracks()
    assert tracks[0].title == "Intro"


def test_local():
    laa = Archivary.Archivary(collection_list=["Local_DeadAndCompany"])
    la = laa.archives[0]
    tape = la.tapes[0]
    print(f"Local tape {tape} has track list {tape.tracks()}")
    assert len(tape.tracks()) > 0


def test_local_multiple():
    collection_list = ["Local_DeadAndCompany", "Local_BobDylan"]
    laa = Archivary.Archivary(collection_list=collection_list)
    la = laa.archives[0]
    artists = [t.artist for t in la.tapes]
    assert sorted(set(artists)) == sorted(set([x.replace("Local_", "") for x in collection_list]))


def test_local_badhome():
    laa = Archivary.Archivary(
        collection_list=["Local_DeadAndCompany"], local_home=os.path.join(os.getenv("HOME"), "non_existant_archive")
    )
    assert laa.archives == []


def test_all_archives():
    config.optd = {
        "COLLECTIONS": ["GratefulDead", "Phish", "PhilLeshandFriends", "TedeschiTrucksBand", "Local_DeadAndCompany"],
        "FAVORED_TAPER": {"UltraMatrix": 10, "miller": 5},
        "PLAY_LOSSLESS": "false",
    }

    aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])
    assert len(aa.archives) == 3


def test_archivary_bad_archive():
    aa = Archivary.Archivary(collection_list=["Phish", "JJJJJXX_ASDF"])
    assert len(aa.archives) == 1


def test_archivary_bad_local_archive():
    aa = Archivary.Archivary(collection_list=["Phish", "Local_JJJJJXX_ASDF"])
    assert len(aa.archives) == 1


def test_archivary_bad_iaarchive():
    aa = Archivary.Archivary(collection_list=["GratefulDead", "JJJJJXX_ASDF"])
    assert len(aa.archives) == 1


def test_archivary_bad_all_archives():
    aa = Archivary.Archivary(collection_list=["ASDF_JJJJJXXX", "Local_JJJJJXX_ASDF"])
    assert len(aa.archives) == 0


def test_archivary_dup_collection():
    collection_list = ["DeadAndCompany", "Local_DeadAndCompany"]
    aa = Archivary.Archivary(collection_list=collection_list)
    tapes = aa.tape_dates["2021-09-18"]
    artists = [t.artist for t in tapes]
    assert sorted(set(artists)) == sorted(set([x.replace("Local_", "") for x in collection_list]))


def test_bad_local_archive():
    local = Archivary.LocalArchive(collection_list=["Local_JJJJJXX_ASDF"])
    assert len(local.dates) == 0


def test_archivary_local_archive_missing_collection():
    # test case where there is a folder in the date which matches date, eg 2000-11-01-disk1
    local = Archivary.LocalArchive(collection_list=["Local_NonExistentCollection"])
    assert len(local.tape_dates) == 0


# def test_archivary_local_archive_bad_folder():
#    # test case where there is a folder in the date which matches date, eg 2000-11-01-disk1
#    local = Archivary.LocalArchive(collection_list=["Local_BadFolder"])
#
#    assert False


def test_gd():
    gd = Archivary.GDArchive()
    tapedate = "1982-11-25"
    tapes = gd.tape_dates[tapedate]
    assert len(tapes) >= 5
    gd_tape = tapes[3]
    assert len(gd_tape.tracks()) > 10


def test_gd_plus():
    gd = Archivary.GDArchive(collection_list=["GratefulDead", "PhilLeshandFriends"])
    tape_dates = gd.tape_dates
    assert max(tape_dates.keys()) > "1996-01-01"
    assert min(tape_dates.keys()) < "1967-01-01"


def test_georgeblood():
    config.optd = {"COLLECTIONS": ["georgeblood"], "FAVORED_TAPER": "miller", "PLAY_LOSSLESS": "false"}
    aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"], date_range=[1930, 1935])
    dates = aa.tape_dates.keys()
    assert min(dates) == "1930-01-01"
    assert max(dates) > "1939-12-01"
    assert len(dates) > 2000


def test_phish():
    config.optd = {"COLLECTIONS": ["Phish"], "FAVORED_TAPER": "miller", "PLAY_LOSSLESS": "false"}
    aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])
    assert len(aa.archives) == 1
    assert len(aa.archives[0].tapes) > 1600


def test_format_1():
    laa = Archivary.Archivary(collection_list=["Local_BobDylan"])
    la = laa.archives[0]
    tape = la.tape_dates["1987-10-12"][0]
    os.system(f"rm {tape.meta_path}")
    tracks = tape.tracks()
    assert tracks[0].title == "Like A Rolling Stone"


def test_small():
    gd = Archivary.GDArchive(collection_list=["DeadAndCompany"])
    tape_dates = gd.tape_dates
    assert max(tape_dates.keys()) > "1996-01-01"
    assert min(tape_dates.keys()) < "1967-01-01"
