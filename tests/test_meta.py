from deadstream.timemachine import MetaAPI


def test_init():
    collection = "DeadAndCompany"
    mapi = MetaAPI.MetaAPI(collection)
    assert isinstance(mapi, MetaAPI.MetaAPI)


def test_phish_urls():
    mapi = MetaAPI.MetaAPI("Phish")
    show = mapi.track_urls("2025-06-24")
    assert isinstance(show, dict)
    assert len(show["tracklist"]) == len(show["urls"])
    assert show["tracklist"][0] == "AC/DC Bag"
    assert show["tracklist"][-1] == "Ghost"


def test_dead_urls():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, dict)
    assert len(show["tracklist"]) == len(show["urls"])
    assert show["tracklist"][0] == "Bill Graham Intro >"
    assert show["tracklist"][-1] == "E: Blues For Allah"
    assert show["urls"][0].endswith(".ogg")


def test_other_urls():
    mapi = MetaAPI.MetaAPI("OteilAndFriends")
    show = mapi.track_urls("2023-07-28")
    assert isinstance(show, dict)
    assert len(show["tracklist"]) == len(show["urls"])
    assert show["tracklist"][0] == "crowd/tuning"
    assert show["urls"][0].endswith(".mp3")


def test_dead_urls_noshow():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-12")  # No show on this date
    assert isinstance(show, dict)
    assert len(show["tracklist"]) == len(show["urls"])
    assert len(show["tracklist"]) == 0


def test_other_urls():
    mapi = MetaAPI.MetaAPI("SteveKimock")
    show = mapi.track_urls("2023-08-04")
    assert isinstance(show, dict)
    assert len(show["tracklist"]) == len(show["urls"])
    assert len(show["tracklist"]) == 9


def test_phish_set_break():
    mapi = MetaAPI.MetaAPI("Phish")
    show = mapi.track_urls("2025-06-24")
    assert isinstance(show, dict)
    assert len(show["tracklist"]) == 16 + 2
    assert len(show["tracklist"]) == len(show["urls"])
    assert show["tracklist"][0] == "AC/DC Bag"
    assert show["tracklist"][-1] == "Ghost"
    assert "Set Break" in show["tracklist"]
    assert "Encore Break" in show["tracklist"]


def test_dead_set_break():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, dict)
    assert "Set Break" in show["tracklist"]
    # assert "Encore Break" in show["tracklist"]
    assert len(show["tracklist"]) == 18 + 1

    show = mapi.track_urls("1977-05-08")
    assert isinstance(show, dict)
    assert "Set Break" in show["tracklist"]
    assert "Encore Break" in show["tracklist"]
    assert len(show["tracklist"]) == 20 + 2


def test_dead_urls_flac_orig():
    # Test a show where the original files are FLAC
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1992-06-25")
    assert isinstance(show, dict)
    assert show["tracklist"][0] == "Tuning"
    assert "Set Break" in show["tracklist"]
    assert "Encore Break" in show["tracklist"]
    assert len(show["tracklist"]) == 22 + 2


def test_dead_urls_tape2():
    # Test a show where the original files are FLAC
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1992-06-25")
    show2 = mapi.track_urls("1992-06-25", tape_no=2)
    assert isinstance(show, dict)
    assert isinstance(show2, dict)
    assert not show["urls"] == show2["urls"]


def test_urls_mp3s():
    # Find a show with mp3 instead of ogg files.
    mapi = MetaAPI.MetaAPI("DeadAndCompany")
    show = mapi.track_urls("2025-08-01")
    assert isinstance(show, dict)
    assert show["urls"][0].endswith(".mp3")
    assert show["tracklist"][0] == "Feel Like a Stranger"
    assert show["tracklist"][-1] == "Not Fade Away"
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
    assert isinstance(show, list)
    assert show[0][0] == "Bill Graham Intro >"
    assert show[-1][0] == "E: Blues For Allah"
    assert show[0][1].endswith(".ogg")


def test_set_breaks():
    set_breaks = MetaAPI.SetBreaks()
    assert len(set_breaks.get_artist_set_dict("GratefulDead")) > 1000
    assert len(set_breaks.get_artist_set_dict("DarkStarOrchestra")) > 100
    assert len(set_breaks.get_artist_set_dict("DeadAndCompany")) > 100
    assert set_breaks.longbreaks("GratefulDead", "1975-08-13")[0] == "Stronger Than Dirt"
    assert set_breaks.longbreaks("GratefulDead", "1977-05-08")[0] == "Dancin' In The Streets"
    assert set_breaks.shortbreaks("GratefulDead", "1977-05-08")[0] == "Morning Dew"
