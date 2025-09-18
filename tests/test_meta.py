from deadstream.timemachine import MetaAPI


def test_init():
    collection = "DeadAndCompany"
    mapi = MetaAPI.MetaAPI(collection)
    assert isinstance(mapi, MetaAPI.MetaAPI)


def test_phish_urls():
    mapi = MetaAPI.MetaAPI("Phish")
    show = mapi.track_urls("2025-06-24")
    assert isinstance(show, MetaAPI.Tape)
    assert len(show.tracklist) == len(show.urls)
    assert show.tracklist[0] == "AC/DC Bag"
    assert show.tracklist[-1] == "Ghost"


def test_phish_pre_show():
    """This show has a pre-show track that led to issues with the Set Break logic"""
    mapi = MetaAPI.MetaAPI("Phish")
    show = mapi.track_urls("2014-06-24")
    # meta = mapi.api_dict["Phish"]._get_raw_meta("2014-06-24")
    assert show.tracklist[0] != "Set Break"


def test_dead_urls():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, MetaAPI.Tape)
    assert len(show.tracklist) == len(show.urls)
    assert show.tracklist[0] == "Bill Graham Intro >"
    assert show.tracklist[-1] == "E: Blues For Allah"
    assert show.urls[0].endswith(".ogg")


def test_other_urls():
    mapi = MetaAPI.MetaAPI("OteilAndFriends")
    show = mapi.track_urls("2023-07-28")
    assert isinstance(show, MetaAPI.Tape)
    assert len(show.tracklist) == len(show.urls)
    assert show.tracklist[0] == "crowd/tuning"
    assert show.urls[0].endswith(".mp3")


def test_multiple_urls():
    mapi = MetaAPI.MetaAPI(["GratefulDead", "Phish"])
    show = mapi.track_urls("1995-07-02")
    assert isinstance(show, MetaAPI.Tape)


def test_dead_urls_noshow():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-12")  # No show on this date
    assert isinstance(show, MetaAPI.Tape)
    assert len(show.tracklist) == len(show.urls)
    assert len(show.tracklist) == 0


def test_other_urls2():
    mapi = MetaAPI.MetaAPI("SteveKimock")
    show = mapi.track_urls("2023-08-04")
    assert isinstance(show, MetaAPI.Tape)
    assert len(show.tracklist) == len(show.urls)
    assert len(show.tracklist) == 9


def test_phish_set_break():
    mapi = MetaAPI.MetaAPI("Phish")
    show = mapi.track_urls("2025-06-24")
    assert isinstance(show, MetaAPI.Tape)
    assert len(show.tracklist) == len(show.urls)
    assert len(show.tracklist) == 16 + 2
    assert show.tracklist[0] == "AC/DC Bag"
    assert show.tracklist[-1] == "Ghost"
    assert "Set Break" in show.tracklist
    assert "Encore Break" in show.tracklist


def test_dead_set_break():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, MetaAPI.Tape)
    assert len(show.tracklist) == len(show.urls)
    assert "Set Break" in show.tracklist
    assert len(show.tracklist) == 18 + 1

    show = mapi.track_urls("1977-05-08")
    assert isinstance(show, MetaAPI.Tape)
    assert "Set Break" in show.tracklist
    assert "Encore Break" in show.tracklist
    assert len(show.tracklist) == 20 + 2


def test_dead_urls_flac_orig():
    # Test a show where the original files are FLAC
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1992-06-25")
    assert isinstance(show, MetaAPI.Tape)
    assert "Set Break" in show.tracklist
    assert show.tracklist[0] == "Tuning"


def test_dead_urls_tape2():
    # Test a show where the original files are FLAC
    mapi = MetaAPI.MetaAPI("GratefulDead")
    show = mapi.track_urls("1992-06-25")
    show2 = mapi.track_urls("1992-06-25", tape_no=2)
    assert isinstance(show, MetaAPI.Tape)
    assert isinstance(show2, MetaAPI.Tape)
    assert not show.urls == show2.urls


def test_urls_mp3s():
    # Find a show with mp3 instead of ogg files.
    mapi = MetaAPI.MetaAPI("DeadAndCompany")
    show = mapi.track_urls("2025-08-01")
    assert isinstance(show, MetaAPI.Tape)
    assert show.urls[0].endswith(".mp3")
    assert show.tracklist[0] == "Feel Like a Stranger"
    assert show.tracklist[-1] == "Not Fade Away"


def test_get_tapes():
    # Find a show with mp3 instead of ogg files.
    mapi = MetaAPI.MetaAPI("GratefulDead")
    tapes = mapi.get_tapes("1992-06-25")
    assert len(tapes) >= 10
    assert tapes[0].track_urls is None  # because we haven't fetched them yet.


def test_get_tapes_multiple_collections():
    # Find a show with mp3 instead of ogg files.
    mapi = MetaAPI.MetaAPI(["GratefulDead", "Phish"])
    tape_dict = mapi.get_tapes("1995-07-02")
    assert isinstance(tape_dict, dict)
    assert len(tape_dict["GratefulDead"]) >= 10
    assert len(tape_dict["Phish"]) == 1


def test_get_meta_date_range():
    # Find a show with mp3 instead of ogg files.
    mapi = MetaAPI.MetaAPI("GratefulDead")
    metadata = mapi.api_dict["GratefulDead"]._get_meta_date_range("1992-06-25", "1993-01-01")
    assert len(metadata["items"]) > 100


def test_get_raw_meta_phish():
    mapi = MetaAPI.MetaAPI("Phish")
    raw_meta = mapi.api_dict["Phish"]._get_raw_meta("2025-06-24")


def test_get_tapes_phish():
    mapi = MetaAPI.MetaAPI("Phish")
    tapes = mapi.get_tapes("2025-06-24")
    assert tapes[0].vcs == "Petersen Events Center, Pittsburgh PA"
    assert tapes[0].id == "phishin_2236"


def test_dead_urls_to_cloud():
    mapi = MetaAPI.MetaAPI("GratefulDead", save_to_cloud=True, bucket_name="spertilo-temporary")
    show = mapi.track_urls("1975-08-13")
    assert isinstance(show, MetaAPI.Tape)
    assert show.tracklist[0] == "Bill Graham Intro >"
    assert show.tracklist[-1] == "E: Blues For Allah"
    assert show.urls[1].endswith(".ogg")


def test_set_breaks():
    set_breaks = MetaAPI.SetBreaks()
    assert len(set_breaks.get_artist_set_dict("GratefulDead")) > 1000
    assert len(set_breaks.get_artist_set_dict("DarkStarOrchestra")) > 100
    assert len(set_breaks.get_artist_set_dict("DeadAndCompany")) > 100
    assert set_breaks.longbreaks("GratefulDead", "1975-08-13")[0] == "Stronger Than Dirt"
    assert set_breaks.longbreaks("GratefulDead", "1977-05-08")[0] == "Dancin' In The Streets"
    assert set_breaks.shortbreaks("GratefulDead", "1977-05-08")[0] == "Morning Dew"


def test_tape_score():
    tape_id = "gd1990-03-29.127385.mtx.eichorn.flac16"
    mapi = MetaAPI.MetaAPI("GratefulDead")
    tapes = mapi.get_tapes("1990-03-29")
    for tape in tapes:
        if tape.id == tape_id:
            break
    score = tape.score
    tracks = mapi.api_dict["GratefulDead"].get_track_urls(tape)
    new_score = tape.score
    assert len(tracks["tracklist"]) == 25
    assert new_score > score


def test_track_name_cleanup():
    tape_id = "gd1990-12-30.141864.UltraMatrix.sbd.cm.miller.flac1644"
    mapi = MetaAPI.MetaAPI("GratefulDead")
    tapes = mapi.get_tapes("1990-12-30")
    for tape in tapes:
        if tape.id == tape_id:
            break
    tracks = mapi.api_dict["GratefulDead"].get_track_urls(tape)
    assert not tracks["tracklist"][0].startswith("01")


def test_get_tapes_trackname_issue():
    mapi = MetaAPI.MetaAPI("EricKrasno")
    date = "2017-05-25"
    tape = mapi.get_tapes(date)[0]
    track_urls = mapi.api_dict["EricKrasno"].get_track_urls(tape)
    assert track_urls["tracklist"][0] == "Intro"
    meta = mapi.api_dict["EricKrasno"]._get_track_data(tape.id)


def test_track_data():
    tape_id = "gd1990-03-29.127385.mtx.eichorn.flac16"
    mapi = MetaAPI.MetaAPI("GratefulDead")
    track_data = mapi.api_dict["GratefulDead"]._get_track_data(tape_id)
    assert track_data["metadata"]["date"] == "1990-03-29"
    assert track_data["metadata"]["venue"] == "Nassau Coliseum"
    assert track_data["metadata"]["coverage"] == "Uniondale, NY"
    assert track_data["metadata"]["title"] == "Grateful Dead Live at Nassau Coliseum on 1990-03-29"

    tapes = mapi.get_tapes("1990-12-30")
    for tape in tapes:
        if tape.id == tape_id:
            break

    tracks = mapi.api_dict["GratefulDead"].get_track_data(tape)
    # The tape should be populated now.
    assert tape.vcs == "Oakland-Alameda County Coliseum, Oakland, CA"


def test_date_meta():
    mapi = MetaAPI.MetaAPI("GratefulDead")
    date = "1990-03-29"
    date_meta = mapi.api_dict["GratefulDead"]._get_meta_date_range(date, date)
    for item in date_meta["items"]:
        assert "identifier" in item.keys()


def test_all_collection_names():
    mapi = MetaAPI.MetaAPI()
    names = mapi.get_all_collection_names()
    assert len(names) > 9000
    assert "GratefulDead" in names
    assert "Phish" in names
    assert "DeadAndCompany" in names
    assert "OteilAndFriends" in names
    assert "SteveKimock" in names
    assert "DarkStarOrchestra" in names
    assert "Furthur" in names
    assert "WidespreadPanic" in names
    assert "moe" in names
    assert "UmphreysMcGee" in names
    assert "BillyAndTheKids" in names


def test_get_vcs_phish():
    mapi = MetaAPI.MetaAPI("Phish")
    vcs = mapi.get_collection_vcs()


def test_get_vcs_archive():
    import datetime

    mapi = MetaAPI.MetaAPI("BigFrog")
    vcs_dict = mapi.get_collection_vcs()
    assert vcs_dict["BigFrog"].get("2003-10-31", None) is not None

    mapi = MetaAPI.MetaAPI(["BigFrog", "EricKrasno"], save_to_cloud=True, bucket_name="spertilo-temporary")
    vcs_dict = mapi.get_collection_vcs()
    assert "BigFrog" in vcs_dict.keys()
    assert "EricKrasno" in vcs_dict.keys()
    ek_dates = vcs_dict["EricKrasno"].keys()
    for ek_date in ek_dates:
        assert len(ek_date) == 10
        datetime.date.fromisoformat(ek_date)  # will raise exception if not valid date
