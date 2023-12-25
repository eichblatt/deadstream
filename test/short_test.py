import json
from threading import Event

from timemachine import Archivary
from timemachine import config
from timemachine import GD
from google.cloud import storage

track_event = Event()

config.load_options()


aa = Archivary.GDArchive(collection_list=["DeadAndCompany"])
tape_dates = aa.tape_dates

print(f"Archivary instantiated {aa}")
storage_client = storage.Client(project="able-folio-397115")
bucket = storage_client.bucket("spertilo-data")
SAVE_TO_CLOUD = True
# SAVE_TO_CLOUD = False


def intersect(lis1, lis2):
    return [x for x in lis1 if x in set(lis2)]


def xcept(lis1, lis2):
    return [x for x in lis1 if not x in set(lis2)]


def save_tapeids_in_cloud(tids, date, collection):
    if not SAVE_TO_CLOUD:
        return ""
    tids_string = json.dumps(tids, indent=1)
    if len(tids_string) == 0:
        return tids_string
    tids_blob_name = f"tapes/{collection}/{date}/tape_ids.json"
    tids_blob = bucket.blob(tids_blob_name)
    tids_blob.upload_from_string(tids_string)
    return tids_string


def save_tape_data_in_cloud(t, date, collection, i_tape):
    if not SAVE_TO_CLOUD:
        return ""
    id = t.identifier
    tracks = t.tracks()
    trackdata = {
        "id": id,
        "collection": collection,
        "venue": t.venue(),
        "tracklist": [x.title for x in tracks],
        "urls": [x.files[0]["url"] for x in tracks],
    }
    trackdata_string = json.dumps(trackdata, indent=1)

    if len(trackdata_string) > 0:
        trackdata_blob_name = f"tapes/{collection}/{date}/{id}/trackdata.json"
        trackdata_blob = bucket.blob(trackdata_blob_name)
        trackdata_blob.upload_from_string(trackdata_string)
    return ""


def get_all_tapes(date, collections=["DeadAndCompany"]):
    global aa
    print(f"Collections is {collections}. Length {len(collections)}, aa.collection_list:{aa.collection_list}")
    colls = intersect(collections, aa.collection_list)
    if collections != [] and len(collections) > len(colls):
        colls_to_add = xcept(collections, aa.collection_list)
        print(f"Need to add collection {colls_to_add}")
        config.optd["COLLECTIONS"] = config.optd["COLLECTIONS"] + colls_to_add
        aa = Archivary.Archivary(collection_list=config.optd["COLLECTIONS"])
    tapes = aa.tape_dates[date]
    get_anything = True
    tape_collections = []
    t = []

    if len(collections) > 0:
        get_anything = False
    for i_tape, tape in enumerate(tapes):
        if get_anything:
            t.append(tape)
            this_collection = tape.collection[0]
            tape_collections.append(this_collection)
            save_tape_data_in_cloud(tape, date, this_collection, i_tape)
        else:
            matches = intersect(collections, tape.collection)
            if len(matches) > 0:
                this_collection = matches[0]
                t.append(tape)
                tape_collections.append(this_collection)
                save_tape_data_in_cloud(tape, date, this_collection, i_tape)
    if len(t) == 0:
        print(f"no tape for {collections} on {date}")
        return {"error": f"no tape for {collections} on {date}"}, []
    else:
        tids = [[x.identifier, x.compute_score()] for x in t]
        save_tapeids_in_cloud(tids, date, this_collection)

    return t, tape_collections
