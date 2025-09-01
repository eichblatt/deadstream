from deadstream.timemachine import MetaAPI


def test_init():
    collection = "DeadAndCompany"
    mapi = MetaAPI.MetaAPI(collection)
    assert isinstance(mapi, MetaAPI.MetaAPI)


def test_phish_urls():
    mapi = MetaAPI.MetaAPI("Phish")
    show = mapi.track_urls("2025-06-24")
    assert isinstance(show, dict)
    assert len(show) == 16
    assert list(show.keys())[0] == "AC/DC Bag"
    assert list(show.keys())[-1] == "Ghost"


def test_dead_urls():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, dict)
    assert list(show.keys())[0] == "Bill Graham Intro >"
    assert list(show.keys())[-1] == "E: Blues For Allah"
    assert list(show.values())[0].endswith(".ogg")


def test_dead_urls_noshow():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-12")  # No show on this date
    assert isinstance(show, dict)
    assert len(show) == 0


def test_other_urls():
    mapi = MetaAPI.MetaAPI("SteveKimock")
    show = mapi.track_urls("2023-08-04")
    assert isinstance(show, dict)
    assert len(show) == 9


def test_phish_set_break():
    mapi = MetaAPI.MetaAPI("Phish")
    show = mapi.track_urls("2025-06-24")
    assert isinstance(show, dict)
    assert len(show) == 16
    assert list(show.keys())[0] == "AC/DC Bag"
    assert list(show.keys())[-1] == "Ghost"
    assert "Set Break" in show.keys()


def test_dead_set_break():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, dict)
    assert "Set Break" in show.keys()
    assert len(show) == 19


def test_dead_urls_flac_orig():
    # Test a show where the original files are FLAC
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1992-06-25")
    assert isinstance(show, dict)
    assert list(show.keys())[0] == "Tuning"
    # assert "Set Break" in show.keys()
    # assert len(show) == 23


def test_dead_urls_tape2():
    # Test a show where the original files are FLAC
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1992-06-25")
    show2 = mapi.track_urls("1992-06-25", tape_no=2)
    assert isinstance(show, dict)
    assert isinstance(show2, dict)
    assert not show == show2


def test_urls_mp3s():
    # Find a show with mp3 instead of ogg files.
    mapi = MetaAPI.MetaAPI("DeadAndCompany")
    show = mapi.track_urls("2025-08-01")
    assert isinstance(show, dict)
    assert list(show.values())[0].endswith(".mp3")
    assert list(show.keys())[0] == "Feel Like a Stranger"
    assert list(show.keys())[-1] == "Not Fade Away"
    # assert "Set Break" in show.keys()
    # assert len(show) == 17


def test_get_tapes():
    # Find a show with mp3 instead of ogg files.
    mapi = MetaAPI.MetaAPI("GratefulDead")
    tapes = mapi.get_tapes("1992-06-25")
    assert len(tapes) >= 10
    assert tapes[0].track_urls is None  # because we haven't fetched them yet.


def test_dead_urls_to_cloud():
    assert False
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, dict)
    assert list(show.keys())[0] == "Bill Graham Intro >"
    assert list(show.keys())[-1] == "E: Blues For Allah"
    assert list(show.values())[0].endswith(".ogg")
