from time import sleep
import difflib
import os
import optparse
import logging
import json
import cherrypy
import subprocess

import pulsectl

from timemachine import bluetoothctl

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
parser = optparse.OptionParser()
parser.add_option('-d', '--debug',
                  dest='debug',
                  type="int",
                  default=0,
                  help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('--options_path',
                  dest='options_path',
                  default=os.path.join(os.getenv('HOME'), '.timemachine_options.txt'),
                  help="path to options file [default %default]")
parser.add_option('--sleep_time',
                  dest='sleep_time',
                  type="int",
                  default=10,
                  help="how long to sleep before checking network status [default %default]")
parser.add_option('-v', '--verbose',
                  dest='verbose',
                  action="store_true",
                  default=False,
                  help="Print more verbose information [default %default]")
parms, remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
if parms.debug:
    logger.setLevel(logging.DEBUG)

bt = None
bt_devices = []
bt_connected = None
bt_connected_device_name = ''
hostname = subprocess.check_output('hostname').decode().strip()
pulse = pulsectl.Pulse('pulsectl')


def default_options():
    d = {}
    d['COLLECTIONS'] = 'GratefulDead'
    d['SCROLL_VENUE'] = 'true'
    d['FAVORED_TAPER'] = 'miller'
    d['AUTO_UPDATE_ARCHIVE'] = 'false'
    d['ON_TOUR_ALLOWED'] = 'false'
    d['BLUETOOTH_ENABLE'] = 'false'
    d['BLUETOOTH_DEVICE'] = 'None'
    d['DEFAULT_START_TIME'] = '15:00:00'
    d['TIMEZONE'] = 'America/New_York'
    return d


def get_collection_names():
    collection_path = os.path.join(os.getenv('HOME'), '.etree_collection_names.json')
    collection_names = []
    try:
        data = json.load(open(collection_path, 'r'))['items']
        collection_names = [x['identifier'] for x in data]
    except Exception:
        logger.warning(F"Failed to read collection names from {collection_path}.")
    finally:
        return collection_names


def read_optd():
    opt_dict_default = default_options()
    opt_dict = opt_dict_default
    try:
        opt_dict = json.load(open(parms.options_path, 'r'))
        extra_keys = [k for k in opt_dict_default.keys() if k not in opt_dict.keys()]
        for k in extra_keys:
            opt_dict[k] = opt_dict_default[k]
    except Exception:
        logger.warning(F"Failed to read options from {parms.options_path}. Using defaults")
    return opt_dict


class OptionsServer(object):
    @cherrypy.expose
    def index(self):
        opt_dict = read_optd()
        logger.debug(F"opt dict {opt_dict}")
        form_strings = [self.get_form_item(x) for x in opt_dict.items() if x[0] not in ['TIMEZONE', 'BLUETOOTH_DEVICE']]
        form_string = '\n'.join(form_strings)
        logger.debug(F"form_string {form_string}")
        tz_list = ["America/New_York", "America/Chicago", "America/Phoenix", "America/Los_Angeles", "America/Mexico_City", "America/Anchorage", "Pacific/Honolulu"]
        tz_strings = [F'<option value="{x}" {self.current_choice(opt_dict,"TIMEZONE",x)}>{x}</option>' for x in tz_list]
        tz_string = '\n'.join(tz_strings)
        logger.debug(f'tz string {tz_string}')

        audio_string = self.get_audio_string()

        bluetooth_button = ""
        if self.current_choice(opt_dict, "BLUETOOTH_ENABLE", 'true'):
            initialize_bluetooth(scan=False)
            bluetooth_button = """
               <form method="get" action="bluetooth_settings">
                 <button type="submit">Bluetooth Settings</button>
               </form> """
        else:
            try:
                bt.send('power off')
            except Exception:
                pass

        page_string = """<html>
         <head></head>
         <body>
           <!-- <meta http-equiv="refresh" content="30"> -->
           <h1> Time Machine Options """ + hostname + """</h1>
           <form method="get" action="save_values">""" + form_string + """
             <label for="timezone"> Choose a Time Zone:</label>
             <select id="timezone" name="TIMEZONE">""" + tz_string + """ </select><p>
             <label for="audio-sink"> Audio Sink:</label>
             <select id="audio-sink" name="audio-sink">""" + audio_string + """ </select><p>
             <button type="submit">Save Values</button>
             <button type="reset">Restore</button>
           </form> """ + bluetooth_button + """
           <form method="get" action="restart_service">
             <button type="submit">Restart Timemachine Service</button>
           </form>
         </body>
        </html>"""
        #  <form method="get" action="update_timemachine">
        #    <button type="submit">Update Timemachine Software</button>
        #  </form>

        return page_string

    def get_audio_string(self):
        global pulse
        audio_string = "headphone jack"
        sink_dict = {}
        sink_list = []
        sink_strings = ''
        try:
            for sink in pulse.sink_list():
                sink_dict[sink.description] = sink.state._value

            sink_list = sorted(sink_dict, key=sink_dict.get)

            sink_strings = [F'<option value="{x}" {x[0]}>{x}</option>' for x in sink_list]
            audio_string = '\n'.join(sink_strings)
        except Exception as e:
            logger.warning("Error in getting audio string")
            logger.warning(f"sink_dict{sink_dict}")
            logger.warning(f"sink_list{sink_list}")
            logger.warning(f"sink_strings{sink_strings}")
            pulse = pulsectl.Pulse('pulsectl')
        logger.debug(f'audio_string {audio_string}')
        return audio_string

    @cherrypy.expose
    def bluetooth_settings(self):

        connected_string = F"<p> Currently connected to {bt_connected_device_name} </p>" if len(bt_connected_device_name) > 0 else ""

        bt_list = [bt_connected_device_name] + [x['name'] for x in bt_devices]
        bt_list = list(dict.fromkeys(bt_list))
        bt_strings = [F'<option value="{x}" {self.current_choice(opt_dict,"BLUETOOTH_DEVICE",x)}>{x}</option>' for x in bt_list]
        bt_device = '\n'.join(bt_strings)
        logger.debug(f'bluetooth devices {bt_device}')

        rescan_bluetooth_string = ""
        bluetooth_device_string = ""
        if self.current_choice(opt_dict, "BLUETOOTH_ENABLE", 'true'):
            rescan_bluetooth_string = """
                <form action="rescan_bluetooth" method="get">
                <button type="submit">Rescan Bluetooth</button>
                </form>  """
            bt_button_label = "Connect Bluetooth Device"
            bluetooth_device_string = """
                <form name="add" action="connect_bluetooth_device" method="post">
                <select name="BLUETOOTH_DEVICE">""" + bt_device + """ </select>
                <button type="submit"> """ + bt_button_label + """ </button> </form>"""

        return_button = """ <form method="get" action="index"> <button type="submit">Return</button> </form> """

        page_string = """
           <html>
               <head></head>
               <body>
                     <h1> Time Machine Bluetooth Settings """ + hostname + """</h1>""" + connected_string + bluetooth_device_string + rescan_bluetooth_string + return_button + """
               </body>
           <html> """
        return page_string

    @cherrypy.expose
    def connect_bluetooth_device(self, BLUETOOTH_DEVICE=None):
        """ set the bluetooth device """
        global bt_connected
        return_button = """ <form method="get" action="bluetooth_settings"> <button type="submit">Return</button> </form> """
        if not BLUETOOTH_DEVICE:
            return return_button

        txt = F"Setting the bluetooth device to {BLUETOOTH_DEVICE}"
        logger.debug("\n\n\n"+txt)

        mac_address = [x['mac_address'] for x in bt_devices if x['name'] == BLUETOOTH_DEVICE][0]
        if not bt.trust(mac_address):
            return F"Failed to Trust {mac_address}" + return_button
        if not bt.pair(mac_address):
            return F"Failed to pair {mac_address}" + return_button
        bt_connected = bt.connect(mac_address)
        if bt_connected:
            opt_dict["BLUETOOTH_DEVICE"] = BLUETOOTH_DEVICE
        return_string = F"Connected to {BLUETOOTH_DEVICE} :)" if bt_connected else F"Failed to connect to {BLUETOOTH_DEVICE} :("
        return_string = return_string + return_button
        return return_string

    def current_choice(self, d, k, v):
        if d[k] == v:
            return "selected"
        else:
            return ""

    def get_form_item(self, item):
        k, v = item
        input_type = "text"
        if type(v) == int:
            input_type = "number"
        outstring = F'<label> {k} <input type="{input_type}" name="{k}" value="{v}"'
        if type(v) == bool:
            outstring += ' pattern="true|false" title="true or false"> <p>'
        else:
            outstring += '> <p>'
        outstring += '</label>'
        return outstring

    def save_options(self, kwargs):
        logger.debug(F"in save_options. kwargs {kwargs}")
        options = {}
        for arg in kwargs.keys():
            if arg == arg.upper():
                options[arg] = kwargs[arg]
        with open(parms.options_path, 'w') as outfile:
            json.dump(options, outfile, indent=1)

    @cherrypy.expose
    def save_values(self, *args, **kwargs):
        collections = kwargs['COLLECTIONS']
        colls = collections.split(',')
        valid_collection_names = get_collection_names()
        proper_collections = []

        for artist in colls:
            artist = artist.replace(" ", "")
            if artist in valid_collection_names:
                proper_collections.append(artist)
            elif artist.lower().strip() == 'phish':
                proper_collections.append('Phish')
            else:
                candidates = difflib.get_close_matches(artist, valid_collection_names, cutoff=0.85)
                if len(candidates) > 0:
                    proper_collections.append(candidates[0])
                else:
                    proper_collections.append(artist)
        kwargs['COLLECTIONS'] = str.join(',', proper_collections)
        logger.debug(F'args: {args},kwargs:{kwargs},\nType: {type(kwargs)}')

        self.save_options(kwargs)
        desired_sink = kwargs['audio-sink']
        if desired_sink != pulse.server_info().default_sink_name:
            for sink in pulse.sink_list():
                if sink.description == desired_sink:
                    pulse.default_set(sink)
                    continue

        form_strings = [F'<label>{x[0]}:{x[1]}</label> <p>' for x in kwargs.items()]
        form_string = '\n'.join(form_strings)
        page_string = """<html>
         <head></head>
             <body> Options set to <p> """ + form_string + """
               <form method="get" action="index">
                 <button type="submit">Return</button>
               </form>
               <form method="get" action="restart_service">
                 <button type="submit">Restart Timemachine Service</button>
               </form>
             </body>
         </html>"""

        sleep(0.2*parms.sleep_time)
        return page_string

    @cherrypy.expose
    def update_timemachine(self, *args, **kwargs):
        cmd = "sudo service update start"
        page_string = """<html>
         <head></head>
         <body> Updating Time Machine <p> Command: """ + cmd + """
           <form method="get" action="index">
#             <button type="submit">Return</button>
             <input class="btn btn-primary" type="submit" name="submit"
             onclick="return confirm('Are you sure?');">
             />
           </form>
          </body>
       </html>"""
        logger.debug(F'Update timemachine command {cmd}')
        sleep(parms.sleep_time)
        os.system(cmd)
        return page_string

    @cherrypy.expose
    def restart_service(self, *args, **kwargs):
        cmd = "sudo service timemachine restart"
        page_string = """<html>
         <head></head>
         <body> Restarting Service <p> Command: """ + cmd + """
           <form method="get" action="index">
             <button type="submit">Return</button>
           </form>
          </body>
       </html>"""
        logger.debug(F'Restart_service command {cmd}')
        sleep(parms.sleep_time)
        os.system(cmd)
        return page_string

    @cherrypy.expose
    def rescan_bluetooth(self, *args, **kwargs):
        global bt_devices
        logger.debug('Rescan bluetooth')

        device_string = ""
        try:
            bt.scan(timeout=15)
            bt_devices = bt.get_candidate_devices()
            logger.debug(F'bt_devices is {bt_devices}')
            device_string = "\n".join([x['name'] for x in bt_devices])
            logger.debug(F'device_string is {device_string}')
        except Exception as e:
            logger.exception(F"Exception in scanning for bluetooth {e}")
            pass

        page_string = """<html>
         <head></head>
         <body> Rescanned for bluetooth devices <p>
           <p> Found: """ + device_string + """ </p>
           <form method="get" action="bluetooth_settings">
             <button type="submit">Return</button>
           </form>
          </body>
        </html>"""

        return page_string


def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(' ')[0]
    return ip


def initialize_bluetooth(scan=True):
    global bt
    global bt_devices
    global bt_connected_device_name
    if not bt:
        bt = bluetoothctl.Bluetoothctl()
    bt.send('power on')
    itry = 0
    while len(bt_connected_device_name) < 1 and itry < 5:
        itry = itry + 1
        logger.debug(F"trying to get device name {itry}")
        bt_connected_device_name = bt.get_connected_device_name()
    if scan or bt_devices == [] and bt_connected_device_name == '':
        bt.scan()
    bt_devices = bt.get_candidate_devices()


opt_dict = read_optd()
logger.debug(F"opt_dict is now {opt_dict}")
if opt_dict['BLUETOOTH_ENABLE'] == 'true':
    initialize_bluetooth(scan=False)


def main():
    ip_address = get_ip()
    cherrypy.config.update({'server.socket_host': ip_address, 'server.socket_port': 9090})
    cherrypy.quickstart(OptionsServer())


for k in parms.__dict__.keys():
    logger.debug(F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug == 0:
    main()
    exit(0)
