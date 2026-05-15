from time import sleep
import difflib
import os
import optparse
import logging
import json
import cherrypy
import subprocess

import pulsectl

from timemachine import bluetoothctl, config

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OS_VERSION = None

parser = optparse.OptionParser()
parser.add_option(
    "-d",
    "--debug",
    dest="debug",
    type="int",
    default=0,
    help="If > 0, don't run the main script on loading [default %default]",
)
parser.add_option(
    "--sleep_time",
    dest="sleep_time",
    type="int",
    default=10,
    help="how long to sleep before checking network status [default %default]",
)
parser.add_option(
    "-v",
    "--verbose",
    dest="verbose",
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
if parms.debug:
    logger.setLevel(logging.DEBUG)


bt = None
bt_devices = []
bt_connected = None
bt_connected_device_name = ""
hostname = subprocess.check_output("hostname").decode().strip()
try:
    pulse = pulsectl.Pulse("pulsectl")
except pulsectl.PulseError:
    pulse = None
    logger.warn("Pulse audio not working on this machine")


def get_os_version():
    global OS_VERSION  # cache the value of os version
    if OS_VERSION is None:
        try:
            cmd = "cat /etc/os-release"
            lines = subprocess.check_output(cmd, shell=True)
            lines = lines.decode().split("\n")
            for line in lines:
                split_line = line.split("=")
                if split_line[0] == "VERSION_ID":
                    OS_VERSION = int(split_line[1].strip('"'))
        except Exception:
            OS_VERSION = 0
            logger.warning("Failed to get OS Version")
    return OS_VERSION


PULSE_ENABLED = get_os_version() > 10


def default_options():
    d = {}
    d["MODULE"] = "livemusic"
    d["COLLECTIONS"] = "GratefulDead"
    d["FAVORED_TAPER"] = "miller"
    d["AUTO_UPDATE_ARCHIVE"] = "true"
    d["UPDATE_ARCHIVE_ON_STARTUP"] = "false"
    d["ON_TOUR_ALLOWED"] = "false"
    d["PLAY_LOSSLESS"] = "false"
    d["PULSEAUDIO_ENABLE"] = "false"
    if get_os_version() > 10:
        d["PULSEAUDIO_ENABLE"] = "true"
        d["BLUETOOTH_ENABLE"] = "true"
        d["BLUETOOTH_DEVICE"] = "None"
    else:
        d["PULSEAUDIO_ENABLE"] = "false"
        d["BLUETOOTH_ENABLE"] = "false"
        d["BLUETOOTH_DEVICE"] = "None"
    d["DEFAULT_START_TIME"] = "15:00:00"
    d["TIMEZONE"] = "America/New_York"
    return d


def get_collection_names():
    collection_path = os.path.join(os.getenv("HOME"), ".etree_collection_names.json")
    collection_names = []
    try:
        data = json.load(open(collection_path, "r"))["items"]
        collection_names = [x["identifier"] for x in data]
    except Exception:
        logger.warning(f"Failed to read collection names from {collection_path}.")
    finally:
        return collection_names


def read_optd():
    global PULSE_ENABLED
    opt_dict_default = default_options()
    opt_dict = opt_dict_default
    try:
        opt_dict = json.load(open(config.OPTIONS_PATH, "r"))
        extra_keys = [k for k in opt_dict_default.keys() if k not in opt_dict.keys()]
        for k in extra_keys:
            opt_dict[k] = opt_dict_default[k]
        if "PULSEAUDIO_ENABLE" in opt_dict.keys():
            PULSE_ENABLED = opt_dict["PULSEAUDIO_ENABLE"] == "true"
    except Exception:
        logger.warning(f"Failed to read options from {config.OPTIONS_PATH}. Using defaults")
    return opt_dict


def restart_pulseaudio():
    cmd = "sudo service pulseaudio restart"
    logger.info(f"restarting pulse audio service {cmd}")
    os.system(cmd)


def stop_pulseaudio():
    cmd = "sudo service pulseaudio stop"
    logger.info(f"STOPPING pulseaudio {cmd}")
    os.system(cmd)


def enable_pulse():
    global pulse
    global PULSE_ENABLED
    if PULSE_ENABLED and pulse is not None:
        return
    try:
        restart_pulseaudio()
        sleep(2)
        pulse = pulsectl.Pulse("pulsectl")
        PULSE_ENABLED = True
    except pulsectl.PulseError:
        pulse = None
        PULSE_ENABLED = False
        logger.warning("Pulse audio not working on this machine")


def disable_pulse():
    global pulse
    global PULSE_ENABLED
    if not PULSE_ENABLED:
        return
    PULSE_ENABLED = False
    try:
        stop_pulseaudio()
        sleep(2)
        pulse = None
    except pulsectl.PulseError:
        pulse = None
        logger.warning("Pulse audio still working on this machine")


STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&family=Righteous&display=swap');

  * { box-sizing: border-box; }

  body {
    margin: 0;
    padding: 24px;
    min-height: 100vh;
    background-color: #0a0018;
    background-image:
      radial-gradient(ellipse at 20% 50%, rgba(120,0,200,0.35) 0%, transparent 55%),
      radial-gradient(ellipse at 80% 15%, rgba(200,0,100,0.35) 0%, transparent 55%),
      radial-gradient(ellipse at 55% 85%, rgba(0,80,200,0.25) 0%, transparent 55%);
    color: #ffd700;
    font-family: 'Fredoka One', 'Trebuchet MS', sans-serif;
    font-size: 18px;
    line-height: 1.6;
  }

  h1 {
    font-family: 'Righteous', Georgia, serif;
    font-size: 2.8em;
    text-align: center;
    color: #ff3dff;
    text-shadow: 0 0 10px #ff3dff, 0 0 30px #ff3dff, 0 0 60px rgba(255,61,255,0.4);
    margin-bottom: 4px;
    letter-spacing: 3px;
  }

  h2 {
    font-family: 'Righteous', Georgia, serif;
    color: #39ff14;
    text-shadow: 0 0 8px #39ff14;
    font-size: 1.1em;
    text-align: center;
    margin-top: 0;
    margin-bottom: 20px;
  }

  h3 { color: #ff9933; font-size: 1em; margin: 8px 0; }

  .card {
    background: rgba(20,0,50,0.75);
    border: 2px solid #6600cc;
    border-radius: 16px;
    padding: 28px 32px;
    max-width: 640px;
    margin: 0 auto 24px;
    box-shadow: 0 0 32px rgba(102,0,204,0.45), inset 0 0 24px rgba(0,0,0,0.4);
  }

  label {
    display: block;
    color: #ffd700;
    margin-top: 14px;
  }

  input[type="text"],
  input[type="number"],
  select {
    background-color: #12002e;
    border: 2px solid #7722cc;
    border-radius: 8px;
    color: #ffd700;
    font-family: 'Fredoka One', sans-serif;
    font-size: 0.95em;
    padding: 6px 12px;
    margin-top: 4px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
    width: 100%;
    max-width: 420px;
  }

  input[type="text"]:focus,
  input[type="number"]:focus,
  select:focus {
    border-color: #ff3dff;
    box-shadow: 0 0 8px rgba(255,61,255,0.55);
  }

  select option { background-color: #12002e; }

  button, input[type="submit"] {
    display: inline-block;
    margin: 8px 8px 0 0;
    padding: 10px 26px;
    border: 2px solid #ff6600;
    border-radius: 50px;
    background: linear-gradient(135deg, #aa0055 0%, #5500aa 100%);
    color: #ffee00;
    font-family: 'Righteous', sans-serif;
    font-size: 0.95em;
    letter-spacing: 1px;
    cursor: pointer;
    text-transform: uppercase;
    box-shadow: 0 0 12px rgba(200,0,100,0.5);
    transition: all 0.18s;
  }

  button:hover, input[type="submit"]:hover {
    background: linear-gradient(135deg, #ff0080 0%, #7700ff 100%);
    box-shadow: 0 0 22px rgba(255,0,128,0.75), 0 0 44px rgba(119,0,255,0.35);
    transform: translateY(-2px);
  }

  button[type="reset"] {
    background: linear-gradient(135deg, #003366 0%, #001133 100%);
    border-color: #0088ff;
  }

  .btn-row { margin-top: 20px; }

  a { color: #39ff14; text-decoration: none; text-shadow: 0 0 6px rgba(57,255,20,0.4); }
  a:hover { text-shadow: 0 0 14px #39ff14; }

  p { margin: 4px 0; }
</style>
"""


class OptionsServer(object):
    def _head(self, title="Time Machine"):
        return f"<head><title>{title}</title>{STYLE}</head>"

    @cherrypy.expose
    def index(self):
        opt_dict = read_optd()
        logger.debug(f"opt dict {opt_dict}")
        form_strings = [
            self.get_form_item(x) for x in opt_dict.items() if x[0] not in ["TIMEZONE", "BLUETOOTH_DEVICE", "MODULE"]
        ]
        form_string = "\n".join(form_strings)
        logger.debug(f"form_string {form_string}")
        tz_list = [
            "America/New_York",
            "America/Chicago",
            "America/Phoenix",
            "America/Los_Angeles",
            "America/Mexico_City",
            "America/Anchorage",
            "Pacific/Honolulu",
        ]
        tz_strings = [f'<option value="{x}" {self.current_choice(opt_dict,"TIMEZONE",x)}>{x}</option>' for x in tz_list]
        tz_string = "\n".join(tz_strings)
        logger.debug(f"tz string {tz_string}")
        module_list = ["livemusic", "78rpm"]
        module_strings = [
            f'<option value="{x}" {self.current_choice(opt_dict,"MODULE",x)}>{x}</option>' for x in module_list
        ]
        module_string = "\n".join(module_strings)
        logger.debug(f"tz string {module_string}")

        audio_string = self.get_audio_string()

        bluetooth_button = ""
        if get_os_version() != 10:
            if self.current_choice(opt_dict, "BLUETOOTH_ENABLE", "true"):
                initialize_bluetooth(scan=False)
                bluetooth_button = """
                   <form method="get" action="bluetooth_settings">
                     <button type="submit">Bluetooth Settings</button>
                   </form> """
            else:
                try:
                    bt.send("power off")
                except Exception:
                    pass

        if pulse is None:
            pulse_string = ""
        else:
            pulse_string = f"""
             <label for="audio-sink"> Audio Sink:</label>
             <select id="audio-sink" name="audio-sink"> {audio_string} </select><p> """

        page_string = f"""<html>
         {self._head("Time Machine Options")}
         <body>
           <h1>&#9760; Time Machine Options &#9760;</h1>
           <h2>{hostname} &mdash; Raspbian {get_os_version()}</h2>
           <div class="card">
             <form method="get" action="save_values">
               <label for="module">Module:</label>
               <select id="module" name="MODULE"> {module_string} </select>
               {form_string}
               <label for="timezone">Time Zone:</label>
               <select id="timezone" name="TIMEZONE"> {tz_string} </select>
               {pulse_string}
               <div class="btn-row">
                 <button type="submit">Save Values</button>
                 <button type="reset">Restore</button>
               </div>
             </form>
           </div>
           <div style="text-align:center">
             {bluetooth_button}
             <form method="get" action="restart_tm_service" style="display:inline">
               <button type="submit">Restart Timemachine</button>
             </form>
             <form method="get" action="restart_options_service" style="display:inline">
               <button type="submit">Restart Options Service</button>
             </form>
           </div>
         </body>
        </html>"""
        #  <form method="get" action="update_timemachine">
        #    <button type="submit">Update Timemachine Software</button>
        #  </form>

        return page_string

    def get_audio_string(self):
        global pulse
        audio_string = "headphone jack"
        if pulse is None:
            return audio_string
        sink_dict = {}
        sink_list = []
        sink_strings = ""
        itry = 0
        while len(sink_list) == 0 and itry < 2 and pulse is not None:  # Try reading again.
            itry = itry + 1
            try:
                sink_list = pulse.sink_list()
            except Exception as e:
                sleep(0.2 * parms.sleep_time)
                logger.warning("delay in getting audio string")

        itry = 0
        while len(sink_list) == 0 and itry < 4 and pulse is not None:  # Try creating a new pulsectl object.
            try:
                pulse = pulsectl.Pulse("pulsectl")
                sink_list = pulse.sink_list()
            except Exception as e:
                itry = itry + 1
                sleep(0.2 * parms.sleep_time)
                logger.warning("Error getting audio string -- creating a new pulsectl object")

        for sink in sink_list:
            sink_dict[sink.description] = sink.state._value

        sink_list = sorted(sink_dict, key=sink_dict.get)

        sink_strings = [f'<option value="{x}" {x[0]}>{x}</option>' for x in sink_list]
        audio_string = "\n".join(sink_strings)

        logger.debug(f"audio_string {audio_string}")
        return audio_string

    @cherrypy.expose
    def bluetooth_settings(self):

        connected_string = (
            f"<p> Currently connected to {bt_connected_device_name} </p>" if len(bt_connected_device_name) > 0 else ""
        )

        bt_list = [bt_connected_device_name] + [x["name"] for x in bt_devices]
        bt_list = list(dict.fromkeys(bt_list))
        bt_strings = [
            f'<option value="{x}" {self.current_choice(opt_dict,"BLUETOOTH_DEVICE",x)}>{x}</option>' for x in bt_list
        ]
        bt_device = "\n".join(bt_strings)
        logger.debug(f"bluetooth devices {bt_device}")

        rescan_bluetooth_string = ""
        bluetooth_device_string = ""
        if self.current_choice(opt_dict, "BLUETOOTH_ENABLE", "true"):
            rescan_bluetooth_string = """
                <form action="rescan_bluetooth" method="get">
                <button type="submit">Rescan Bluetooth</button>
                </form>  """
            bt_button_label = "Connect Bluetooth Device"
            bluetooth_device_string = f"""
                <form name="add" action="connect_bluetooth_device" method="post">
                <select name="BLUETOOTH_DEVICE"> {bt_device} </select>
                <button type="submit"> {bt_button_label} </button> </form>"""

        return_button = """ <form method="get" action="index"> <button type="submit">Return</button> </form> """

        notes_string = """<h2> Note: Connecting to bluetooth is NOT intended to be possible while tripping!!! </h2>
            <h3> After connecting a bluetooth device, you will need to set the AUDIO SINK on the main page to send the audio to the connected bluetooth device </h3>
            <h3> After pointing the AUDIO SINK, you may need to SAVE VALUES and refresh the web browser for the change to take effect </h3>
            <h3> Make sure that nothing is ALREADY connected to the Bluetooth device you are trying to connect to. </h3> 
            <h3> Every Bluetooth device may behave differently. Your device may refuse to connect, and we probably cannot help solve it!  </h3>
            <h3> See <a href=https://www.spertilo.net/compatible-bluetooth-devices> https://www.spertilo.net/compatible-bluetooth-devices </a> for a list of known compatible devices </h3> """
        page_string = f"""
           <html>
               {self._head("Bluetooth Settings")}
               <body>
                 <h1>&#9760; Bluetooth Settings &#9760;</h1>
                 <h2>{hostname}</h2>
                 <div class="card">
                   {notes_string}
                   {connected_string}
                   {bluetooth_device_string}
                   <div class="btn-row">{rescan_bluetooth_string} {return_button}</div>
                 </div>
               </body>
           </html>"""
        return page_string

    @cherrypy.expose
    def connect_bluetooth_device(self, BLUETOOTH_DEVICE=None):
        """set the bluetooth device"""
        global bt_connected
        return_button_success = """ <form method="get" action="index"> <button type="submit">Return</button> </form> """
        return_button_fail = (
            """ <form method="get" action="bluetooth_settings"> <button type="submit">Return</button> </form> """
        )
        if not BLUETOOTH_DEVICE:
            return return_button_success

        txt = f"Setting the bluetooth device to {BLUETOOTH_DEVICE}"
        logger.warning("\n\n\n" + txt)

        mac_address = [x["mac_address"] for x in bt_devices if x["name"] == BLUETOOTH_DEVICE][0]
        if not bt.trust(mac_address):
            return f"Failed to Trust {mac_address} {return_button_fail}"
        if not bt.pair(mac_address):
            return f"Failed to pair {mac_address} {return_button_fail}"
        bt_connected = bt.connect(mac_address)
        if bt_connected:
            opt_dict["BLUETOOTH_DEVICE"] = BLUETOOTH_DEVICE
        return_string = (
            f"Connected to {BLUETOOTH_DEVICE} :)" if bt_connected else f"Failed to connect to {BLUETOOTH_DEVICE} :("
        )
        return_string = return_string + (return_button_success if bt_connected else return_button_fail)
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
        outstring = f'<label> {k} <input type="{input_type}" name="{k}" value="{v}"'
        if type(v) == bool:
            outstring += ' pattern="true|false" title="true or false"> <p>'
        else:
            if k == "COLLECTIONS":
                outstring += '> see the <a href=https://archive.org/browse.php?collection=etree&field=creator target="_blank"> list of live music collection names </a>'
                outstring += f"<p>Current Selection: {v} <p"
            outstring += "> <p>"
        outstring += "</label>"
        return outstring

    def save_options(self, kwargs):
        logger.debug(f"in save_options. kwargs {kwargs}")
        options = {}
        for arg in kwargs.keys():
            if arg == arg.upper():
                options[arg] = kwargs[arg]
        with open(config.OPTIONS_PATH, "w") as outfile:
            json.dump(options, outfile, indent=1)

    def set_pulse_values(self, pulse, desired_sink):
        if pulse is None:
            return
        current_sink_name = pulse.server_info().default_sink_name
        current_sink_desc = [x.description for x in pulse.sink_list() if x.name == current_sink_name][0]
        if desired_sink != current_sink_desc:
            logger.warning(
                f"\n\n\n\nresetting pulseaudio service. desired sink {desired_sink} <> {pulse.server_info().default_sink_name}"
            )
            for sink in pulse.sink_list():
                if sink.description == desired_sink:
                    logger.warning(f"\n\n\n\n{desired_sink} found")
                    pulse.default_set(sink)
                    logger.warning(f"\n\n\n\nsink is now {pulse.server_info().default_sink_name}")
                    # restart_pulseaudio()
                    continue

    @cherrypy.expose
    def save_values(self, *args, **kwargs):
        collections = kwargs["COLLECTIONS"]
        colls = collections.split(",")
        valid_collection_names = get_collection_names()
        proper_collections = []

        for artist in colls:
            artist = artist.replace(" ", "")
            if artist in valid_collection_names:
                proper_collections.append(artist)
            elif artist.lower().strip() == "phish":
                proper_collections.append("Phish")
            elif artist.startswith('"') and artist.endswith('"'):
                proper_collections.append(artist.replace('"', ""))
            else:
                candidates = difflib.get_close_matches(artist, valid_collection_names, cutoff=0.7)
                if len(candidates) > 0:
                    proper_collections.append(candidates[0])
                else:
                    proper_collections.append(artist)
        kwargs["COLLECTIONS"] = str.join(",", proper_collections)
        logger.debug(f"args: {args},kwargs:{kwargs},\nType: {type(kwargs)}")

        self.save_options(kwargs)

        if opt_dict["MODULE"] == kwargs["MODULE"]:
            logger.info(f"Current choice of module is unchanged")
        else:
            self.restart_tm_service()
        if kwargs["PULSEAUDIO_ENABLE"] == "true":
            logger.info(f"kwargs['PULSEAUDIO_ENABLE'] is {kwargs}")
            enable_pulse()
        else:
            logger.info(f"kwargs['PULSEAUDIO_ENABLE'] is false")
            disable_pulse()
            disable_bluetooth()

        try:
            desired_sink = kwargs["audio-sink"]
        except KeyError:
            logger.warning("audio-sink not in kwargs")
            desired_sink = "headphone jack"

        self.set_pulse_values(pulse, desired_sink)

        form_strings = [f"<label>{x[0]}:{x[1]}</label> <p>" for x in kwargs.items()]
        form_string = "\n".join(form_strings)
        page_string = f"""<html>
         {self._head("Options Saved")}
         <body>
           <h1>&#9760; Options Saved &#9760;</h1>
           <div class="card">
             {form_string}
             <div class="btn-row">
               <form method="get" action="index" style="display:inline">
                 <button type="submit">Return</button>
               </form>
               <form method="get" action="restart_tm_service" style="display:inline">
                 <button type="submit">Restart Timemachine</button>
               </form>
               <form method="get" action="restart_options_service" style="display:inline">
                 <button type="submit">Restart Options Service</button>
               </form>
             </div>
           </div>
         </body>
         </html>"""

        sleep(0.2 * parms.sleep_time)
        return page_string

    @cherrypy.expose
    def update_timemachine(self, *args, **kwargs):
        cmd = "sudo service update start"
        page_string = f"""<html>
         {self._head("Updating Time Machine")}
         <body>
           <h1>&#9760; Updating Time Machine &#9760;</h1>
           <div class="card">
             <p>Command: <code>{cmd}</code></p>
             <div class="btn-row">
               <form method="get" action="index" style="display:inline">
                 <input type="submit" value="Return" onclick="return confirm('Are you sure?');">
               </form>
             </div>
           </div>
         </body>
       </html>"""
        logger.debug(f"Update timemachine command {cmd}")
        sleep(parms.sleep_time)
        os.system(cmd)
        return page_string

    @cherrypy.expose
    def restart_tm_service(self, *args, **kwargs):
        return self.restart_service(service_name="timemachine")

    @cherrypy.expose
    def restart_options_service(self, *args, **kwargs):
        return self.restart_service(service_name="serve_options")

    @cherrypy.expose
    def restart_service(self, *args, **kwargs):
        action = kwargs.get("action", "restart")
        cmd = f"sudo service {kwargs['service_name']} {action}"
        page_string = f"""<html>
         {self._head("Restarting Service")}
         <body>
           <h1>&#9760; Restarting Service &#9760;</h1>
           <div class="card">
             <p>Command: <code>{cmd}</code></p>
             <div class="btn-row">
               <form method="get" action="index" style="display:inline">
                 <button type="submit">Return</button>
               </form>
             </div>
           </div>
         </body>
         </html>"""
        logger.info(f"Restart_service command {cmd}")
        sleep(parms.sleep_time)
        os.system(cmd)
        return page_string

    @cherrypy.expose
    def rescan_bluetooth(self, *args, **kwargs):
        global bt_devices
        logger.debug("Rescan bluetooth")

        device_string = ""
        try:
            bt.scan(timeout=15)
            bt_devices = bt.get_candidate_devices()
            logger.debug(f"bt_devices is {bt_devices}")
            device_string = "\n".join([x["name"] for x in bt_devices])
            logger.debug(f"device_string is {device_string}")
        except Exception as e:
            logger.exception(f"Exception in scanning for bluetooth {e}")
            pass

        page_string = f"""<html>
         {self._head("Bluetooth Scan")}
         <body>
           <h1>&#9760; Bluetooth Scan &#9760;</h1>
           <div class="card">
             <p>Found: {device_string}</p>
             <div class="btn-row">
               <form method="get" action="bluetooth_settings" style="display:inline">
                 <button type="submit">Return</button>
               </form>
             </div>
           </div>
         </body>
        </html>"""

        return page_string


def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(" ")[0]
    return ip


def initialize_bluetooth(scan=True):
    global bt
    global bt_devices
    global bt_connected_device_name
    if not bt:
        bt = bluetoothctl.Bluetoothctl()
    bt.send("power on")
    itry = 0
    while len(bt_connected_device_name) < 1 and itry < 5:
        itry = itry + 1
        logger.debug(f"trying to get device name {itry}")
        bt_connected_device_name = bt.get_connected_device_name()
    if scan or bt_devices == [] and bt_connected_device_name == "":
        bt.scan()
    bt_devices = bt.get_candidate_devices()


def disable_bluetooth():
    global opt_dict
    try:
        bt.send("power off")
        opt_dict["BLUETOOTH_ENABLE"] = "false"
        config.save_options(opt_dict)
    except Exception:
        pass


opt_dict = read_optd()
logger.debug(f"opt_dict is now {opt_dict}")

if opt_dict["PULSEAUDIO_ENABLE"] == "true":
    enable_pulse()
    if (get_os_version() > 10) and opt_dict["BLUETOOTH_ENABLE"] == "true":
        initialize_bluetooth(scan=False)


def main():
    ip_address = get_ip()
    cherrypy.config.update({"server.socket_host": ip_address, "server.socket_port": 9090})
    cherrypy.quickstart(OptionsServer())


for k in parms.__dict__.keys():
    logger.debug(f"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug == 0:
    main()
    exit(0)
