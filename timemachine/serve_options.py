from time import sleep
import difflib
import os
import optparse
import logging
import json
import cherrypy
import subprocess


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


def default_options():
    d = {}
    d['COLLECTIONS'] = 'GratefulDead'
    d['SCROLL_VENUE'] = 'true'
    d['FAVORED_TAPER'] = 'miller'
    d['AUTO_UPDATE_ARCHIVE'] = 'false'
    d['ON_TOUR_ALLOWED'] = 'false'
    d['DEFAULT_START_TIME'] = '15:00:00'
    d['TIMEZONE'] = 'America/New_York'
    return d


def get_collection_names():
    collection_path = os.path.join(os.getenv('HOME'), '.etree_collection_names')
    collection_names = []
    try:
        with open(collection_path, 'r') as inpath:
            collection_names = inpath.readlines()
        collection_names = [x.strip() for x in collection_names]
    except Exception as e:
        logger.warning(F"Failed to read collection names from {collection_path}.")
    finally:
        return collection_names


class StringGenerator(object):
    @cherrypy.expose
    def index(self):
        opt_dict_default = default_options()
        opt_dict = opt_dict_default
        try:
            opt_dict = json.load(open(parms.options_path, 'r'))
            extra_keys = [k for k in opt_dict_default.keys() if k not in opt_dict.keys()]
            for k in extra_keys:
                opt_dict[k] = opt_dict_default[k]
        except Exception as e:
            logger.warning(F"Failed to read options from {parms.options_path}. Using defaults")
        print(F"opt dict {opt_dict}")
        form_strings = [self.get_form_item(x) for x in opt_dict.items() if x[0] != 'TIMEZONE']
        # form_strings = [F'<label>{x[0]} <input type="text" value="{x[1]}" name="{x[0]}" /></label> <p>' for x in opt_dict.items() if  x[0]!='TIMEZONE']
        form_string = '\n'.join(form_strings)
        print(F"form_string {form_string}")
        tz_list = ["America/New_York", "America/Chicago", "America/Phoenix", "America/Los_Angeles", "America/Mexico_City", "America/Anchorage", "Pacific/Honolulu"]
        tz_strings = [F'<option value="{x}" {self.current_choice(opt_dict,"TIMEZONE",x)}>{x}</option>' for x in tz_list]
        tz_string = '\n'.join(tz_strings)
        logger.info(f'tz string {tz_string}')
        hostname = subprocess.check_output('hostname').decode().strip()
        page_string = """<html>
         <head></head>
         <body>
           <h1> Time Machine Options """ + hostname + """</h1>
           <form method="get" action="save_values">""" + form_string + """
             <label for="timezone"> Choose a Time Zone:</label>
             <select id="timezone" name="TIMEZONE">""" + tz_string + """ </select><p>
             <button type="submit">Save Values</button>
             <button type="reset">Restore</button>
           </form>
           <form method="get" action="restart_service">
             <button type="submit">Restart Timemachine Service</button>
           </form>
         </body>
        </html>"""
        #  <form method="get" action="update_timemachine">
        #    <button type="submit">Update Timemachine Software</button>
        #  </form>

        return page_string

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
        with open(parms.options_path, 'w') as outfile:
            opt_dict = json.dump(kwargs, outfile, indent=1)
        print(F'args: {args},kwargs:{kwargs},\nType: {type(kwargs)}')
        form_strings = [F'<label>{x[0]}:{x[1]}</label> <p>' for x in kwargs.items()]
        form_string = '\n'.join(form_strings)
        page_string = """<html>
         <head></head>
         <body> Options set to <p> """ + form_string + """
           <form method="get" action="index">
             <button type="submit">Return</button>
           </form>
         </body>
       </html>"""
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
        print(F'Update timemachine command {cmd}')
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
        print(F'Restart_service command {cmd}')
        sleep(parms.sleep_time)
        os.system(cmd)
        return page_string


def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(' ')[0]
    return ip


def main():
    ip_address = get_ip()
    cherrypy.config.update({'server.socket_host': ip_address, 'server.socket_port': 9090})
    cherrypy.quickstart(StringGenerator())


for k in parms.__dict__.keys():
    print(F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug == 0:
    main()
    exit(0)
