# Display driver: https://github.com/russhughes/st7789_mpy
import json
import os
import re
import network
import sys
import time
from mrequests import mrequests as requests

import machine
import st7789
import fonts.DejaVu_20x as date_font
import fonts.DejaVu_33 as large_font
import fonts.NotoSans_18 as pfont_small
import fonts.NotoSans_24 as pfont_med
import fonts.NotoSans_32 as pfont_large
from machine import SPI, Pin
from rotary_irq_esp import RotaryIRQ
import network

import board as tm
import utils


machine.freq(240_000_000)
API = 'http://westmain:5000' # westmain
#API = 'http://192.168.1.235:5000' # westmain
#API = 'http://deadstreamv3:5000'


print("Starting...")


def set_date(date):
    tm.y._value = int(date[:4])
    tm.m._value = int(date[5:7])
    tm.d._value = int(date[8:10])
    key_date = f"{tm.y.value()}-{tm.m.value():02d}-{tm.d.value():02d}"
    return key_date


def best_tape(collection, key_date):
    pass


def select_date(collections, key_date, ntape=0):
    print(f"selecting show from {key_date}")
    collstring = ",".join(collections)
    api_request = f"{API}/tracklist/{key_date}?collections={collstring}&ntape={ntape}" 
    print(f"API request is {api_request}")
    resp = requests.get(api_request).json()
    collection = resp['collection']
    tracklist = resp['tracklist']
    api_request = f"{API}/urls/{key_date}?collections={collstring}&ntape={ntape}" 
    resp = requests.get(api_request).json()
    urls = resp['urls']
    print(f"URLs: {urls}")
    return collection, tracklist, urls

def get_tape_ids(collections,key_date):
    print(f"getting tape_ids from {key_date}")
    collstring = ",".join(collections)
    api_request = f"{API}/tape_ids/{key_date}?collections={collstring}"
    print(f"API request is {api_request}")
    tape_ids = requests.get(api_request).json()
    return tape_ids
     

stage_date_bbox = utils.Bbox(0,0,160,32)
nshows_bbox = utils.Bbox(150,32,160,48)
venue_bbox = utils.Bbox(0,32,160,32+20)
artist_bbox = utils.Bbox(0,52,160,52+20)
tracklist_bbox = utils.Bbox(0,70, 160, 110)
selected_date_bbox = utils.Bbox(15,113,145,128)
playpause_bbox = utils.Bbox(145 ,113, 160, 128)

stage_date_color = st7789.color565(255, 255, 0)
yellow_color = st7789.color565(255, 255, 0)
tracklist_color = st7789.color565(0, 255, 255)
play_color = st7789.color565(255, 0, 0)
nshows_color = st7789.color565(0, 100, 255)

def display_tracks(current_track_name,next_track_name):
    utils.clear_bbox(tracklist_bbox)
    tm.tft.write(pfont_small, f"{current_track_name}", tracklist_bbox.x0, tracklist_bbox.y0, tracklist_color)
    tm.tft.write(pfont_small, f"{next_track_name}", tracklist_bbox.x0, tracklist_bbox.center()[1], tracklist_color)
    return 

def main_loop(coll_dict):
    year_old = -1
    month_old = -1
    day_old = -1
    date_old = ""
    PowerLED = True
    pPower_old = False
    pSelect_old = False
    pPlayPause_old = False
    pStop_old = False
    pRewind_old = False
    pFFwd_old = False
    pYSw_old = False
    pMSw_old = False
    pDSw_old = False
    key_date = set_date('1989-08-13')
    selected_date = key_date
    playstate = 0
    collection = "GratefulDead"; tracklist = []; urls = []
    collections = list(coll_dict.keys())
    current_collection = ''
    current_track_index = -1
    current_track_name = next_track_name = '' 
    select_press_time = 0
    power_press_time = 0
    ntape = 0
    valid_dates = set()
    for c in collections:
        valid_dates = valid_dates | set(list(coll_dict[c].keys()))
    del c
    valid_dates = list(sorted(valid_dates))
    utils.clear_screen()

    while True:
        nshows = 0
        
        if pPower_old != tm.pPower.value():
            pPower_old = tm.pPower.value()
            tm.pLED.value(PowerLED)
            tm.tft.off() if not PowerLED else tm.tft.on()
            if pPower_old:
                print("Power UP")
            else:
                PowerLED = not PowerLED
                power_press_time = time.ticks_ms()
                print("Power DOWN -- screen")

        if not tm.pPower.value():
            if (time.ticks_ms()-power_press_time) > 1_000:
                select_press_time = time.ticks_ms()
                print("Power DOWN -- exiting")
                tm.tft.off() 
                time.sleep(0.1)
                sys.exit()

        if pSelect_old != tm.pSelect.value():
            pSelect_old = tm.pSelect.value()
            if pSelect_old:
                if key_date in valid_dates:
                    current_track_index = 0
                    collection, tracklist, urls = select_date(coll_dict.keys(),key_date, ntape)
                    vcs = coll_dict[collection][key_date]
                    ntape = 0
                    current_collection = collection
                    current_track_name = tracklist[current_track_index]
                    next_track_name = tracklist[current_track_index+1] if len(tracklist)> current_track_index else ''
                    display_tracks(current_track_name,next_track_name)

                    selected_date = key_date
                    utils.clear_bbox(venue_bbox)
                    tm.tft.write(pfont_small, f"{vcs}", venue_bbox.x0, venue_bbox.y0, stage_date_color) # no need to clear this.
                    utils.clear_bbox(selected_date_bbox)
                    tm.tft.write(date_font, f"{int(selected_date[5:7]):2d}-{selected_date[8:10]}-{selected_date[:4]}",
                              selected_date_bbox.x0,selected_date_bbox.y0)
                print("Select UP")
            else:
                select_press_time = time.ticks_ms()
                print("Select DOWN")

        if not tm.pSelect.value():
            if (time.ticks_ms()-select_press_time) > 1_000:
                select_press_time = time.ticks_ms()
                if ntape == 0:
                    tape_ids = get_tape_ids(coll_dict.keys(),key_date)
                ntape = (ntape + 1)%len(tape_ids)
                utils.clear_bbox(artist_bbox)
                tm.tft.write(pfont_small, f"{tape_ids[ntape][0]}", artist_bbox.x0, artist_bbox.y0, stage_date_color) 
                #vcs = coll_dict[tape_ids[ntape][0]][key_date]
                utils.clear_bbox(venue_bbox)
                display_str = re.sub(r"\d\d\d\d-\d\d-\d\d\.*","~", tape_ids[ntape][1])
                display_str = re.sub(r"\d\d-\d\d-\d\d\.*","~", display_str)
                print(f"display string is {display_str}")
                if len(display_str) > 18:
                    display_str = display_str[:11] + display_str[-6:]
                tm.tft.write(pfont_small, f"{display_str}", venue_bbox.x0, venue_bbox.y0, stage_date_color) # no need to clear this.
                print(f"Select LONG_PRESS values is {tm.pSelect.value()}. ntape = {ntape}")

        
        if pPlayPause_old != tm.pPlayPause.value():
            pPlayPause_old = tm.pPlayPause.value()
            if pPlayPause_old:
                print("PlayPause UP")
            else:
                playstate = 1 if playstate == 0 else 0
                utils.clear_bbox(playpause_bbox)
                if playstate > 0:
                    print(f"Playing URL {urls[current_track_index]}")
                    tm.tft.fill_polygon(tm.PlayPoly, playpause_bbox.x0, playpause_bbox.y0 , play_color)
                else:
                    print(f"Pausing URL {urls[current_track_index]}")
                    tm.tft.fill_polygon(tm.PausePoly, playpause_bbox.x0, playpause_bbox.y0 , st7789.WHITE)
                print("PlayPause DOWN")

        if pStop_old != tm.pStop.value():
            pStop_old = tm.pStop.value()
            if pStop_old:
                print("Stop UP")
            else:
                print("Stop DOWN")

        if pRewind_old != tm.pRewind.value():
            pRewind_old = tm.pRewind.value()
            if pRewind_old:
                # tm.tft.fill_polygon(tm.RewPoly, 30, 108, st7789.BLUE)
                print("Rewind UP")
            else:
                # tm.tft.fill_polygon(tm.RewPoly, 30, 108, st7789.WHITE)
                print("Rewind DOWN")
                if current_track_index <= 0:
                    pass
                elif current_track_index>=0:
                    current_track_index += -1
                    current_track_name = tracklist[current_track_index]
                    next_track_name = tracklist[current_track_index+1] if len(tracklist) > current_track_index + 1 else ''
                    display_tracks(current_track_name,next_track_name)




        if pFFwd_old != tm.pFFwd.value():
            pFFwd_old = tm.pFFwd.value()
            if pFFwd_old:
                # tm.tft.fill_polygon(tm.FFPoly, 80, 108, st7789.BLUE)
                print("FFwd UP")
            else:
                # tm.tft.fill_polygon(tm.FFPoly, 80, 108, st7789.WHITE)
                print("FFwd DOWN")
                if current_track_index >= len(tracklist):
                    pass
                elif current_track_index>=0:
                    current_track_index += 1 if len(tracklist)> current_track_index + 1 else 0
                    current_track_name = tracklist[current_track_index]
                    next_track_name = tracklist[current_track_index+1] if len(tracklist) > current_track_index + 1 else ''
                    display_tracks(current_track_name,next_track_name)

        if pYSw_old != tm.pYSw.value():
            pYSw_old = tm.pYSw.value()
            if pYSw_old:
                print("Year UP")
            else:
                # cycle through Today In History (once we know what today is!)
                print("Year DOWN")

        if pMSw_old != tm.pMSw.value():
            pMSw_old = tm.pMSw.value()
            if pMSw_old:
                print("Month UP")
            else:
                print("Month DOWN")

        if pDSw_old != tm.pDSw.value():
            pDSw_old = tm.pDSw.value()
            if pDSw_old:
                print("Day UP")
            else:
                for date in valid_dates:
                    if date > key_date:
                        key_date = set_date(date)
                        break
                print("Day DOWN")

        year_new = tm.y.value()
        month_new = tm.m.value()
        day_new = tm.d.value()
        if (month_new in [4, 6, 9, 11]) and (day_new > 30):
            day_new = 30
        if (month_new == 2) and (day_new > 28):
            if year_new % 4 == 0:
                day_new = min(29, day_new)
                if (year_new % 100 == 0) and (year_new % 400 != 0):
                    day_new = min(28, day_new)
            else:
                day_new = min(28, day_new)

        date_new = f"{month_new:2d}-{day_new:02d}-{year_new%100:02d}"
        key_date = f"{year_new}-{month_new:02d}-{day_new:02d}"
        key_date = set_date(key_date)
        if year_old != year_new:
            year_old = year_new
            print("year =", year_new)

        if month_old != month_new:
            month_old = month_new
            print("month =", month_new)

        if day_old != day_new:
            day_old = day_new
            print("day =", day_new)

        if date_old != date_new:
            utils.clear_bbox(stage_date_bbox)
            tm.tft.write(large_font, f"{date_new}", 0, 0, stage_date_color) # no need to clear this.
            # tm.tft.text(font, f"{date_new}", 0, 0, stage_date_color, st7789.BLACK) # no need to clear this.
            date_old = date_new
            print(f"date = {date_new} or {key_date}")
            try:
                if key_date in valid_dates:
                    for c in list(coll_dict.keys()):
                        if key_date in coll_dict[c].keys():
                            nshows += 1
                            collection = c
                            vcs = coll_dict[collection][f"{key_date}"]
                            utils.clear_bbox(artist_bbox)
                            tm.tft.write(pfont_small, f"{collection}", artist_bbox.x0, artist_bbox.y0, stage_date_color) 
                else:
                    vcs = ''
                    collection = ''
                    utils.clear_bbox(artist_bbox)
                    tm.tft.write(pfont_small, f"{current_collection}", artist_bbox.x0, artist_bbox.y0, tracklist_color) 
                    display_tracks(current_track_name,next_track_name)
                print(f'vcs is {vcs}')
                utils.clear_bbox(venue_bbox)
                tm.tft.write(pfont_small, f"{vcs}", venue_bbox.x0, venue_bbox.y0, stage_date_color) # no need to clear this.
                utils.clear_bbox(nshows_bbox)
                if nshows > 1:
                    tm.tft.write(pfont_small, f"{nshows}", nshows_bbox.x0, nshows_bbox.y0, nshows_color) # no need to clear this.
            except KeyError:
                utils.clear_bbox(venue_bbox)
                utils.clear_bbox(artist_bbox)
                tm.tft.write(pfont_small, f"{current_collection}", artist_bbox.x0, artist_bbox.y0, stage_date_color) 
                display_tracks(current_track_name,next_track_name)
                pass
        # time.sleep_ms(50)


def add_vcs(coll):
    ids_path = f"metadata/{coll}_vcs.json"
    print(f"Loading collection {coll} from {ids_path}")
    api_request = f"{API}/vcs/{coll}" 
    resp = requests.get(api_request).json()
    vcs = resp[coll]
    print(f"vcs: {vcs}")
    with open(ids_path,'w') as f:
        json.dump(vcs,f)
    

def load_vcs(coll):
    ids_path = f"metadata/{coll}_vcs.json"
    if not utils.path_exists(ids_path):
        add_vcs(coll)
    print(f"Loading collection {coll} from {ids_path}")
    data = json.load(open(ids_path, "r"))
    return data


def lookup_date(d, col_d):
    response = []
    for col, data in col_d.items():
        if d in data.keys():
            response.append([col, data[d]])
    return response


def main():
    """
    This script will load a super-compressed version of the
    date, artist, venue, city, state.
    """
    utils.clear_screen()
    tm.tft.write(pfont_med, "Connecting", 0, 0, yellow_color)
    tm.tft.write(pfont_med, "WiFi...", 0, 30, yellow_color)
    wifi = utils.connect_wifi()
    ip_address = wifi.ifconfig()[0]
    tm.tft.write(pfont_med, ip_address, 0, 60, st7789.WHITE)

    collection_list_path = 'collection_list.json'
    if utils.path_exists(collection_list_path):
        collection_list = json.load(open(collection_list_path, "r"))
    else:
        collection_list = ['GratefulDead']
        with open(collection_list_path,'w') as f:
            json.dump(collection_list,f)

    coll_dict = {}
    min_year = tm.y._min_val
    max_year = tm.y._max_val
    for coll in collection_list:
        coll_dict[coll] = load_vcs(coll)
        coll_dates = coll_dict[coll].keys()
        min_year = min(int(min(coll_dates)[:4]),min_year)
        max_year = max(int(max(coll_dates)[:4]),max_year)
        tm.y._min_val = min_year
        tm.y._max_val = max_year


    print(f"Loaded collections {coll_dict.keys()}")

    main_loop(coll_dict)

main()
