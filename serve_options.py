from timemachine import config
from time import sleep
from threading import Event
import datetime
import string
import os
import optparse
import logging
import json
import pkg_resources
import cherrypy
import subprocess


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
parser = optparse.OptionParser()
parser.add_option('-d', '--debug', dest='debug', type="int", default=1, help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('--options_path', dest='options_path', default=os.path.join(ROOT_DIR, 'timemachine', 'options.txt'), help="path to options file [default %default]")
parser.add_option('--sleep_time', dest='sleep_time', type="int", default=10, help="how long to sleep before checking network status [default %default]")
parser.add_option('-v', '--verbose', dest='verbose', action="store_true", default=False, help="Print more verbose information [default %default]")
parms, remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)


class StringGenerator(object):
    @cherrypy.expose
    def index(self):
        f = open(parms.options_path, 'r')
        opt_dict = json.loads(f.read())
        print(F"opt dict {opt_dict}")
        form_strings = [self.get_form_item(x) for x in opt_dict.items() if x[0] != 'TIMEZONE']
        #form_strings = [F'<label>{x[0]} <input type="text" value="{x[1]}" name="{x[0]}" /></label> <p>' for x in opt_dict.items() if  x[0]!='TIMEZONE']
        form_string = '\n'.join(form_strings)
        print(F"form_string {form_string}")
        tz_list = ["America/New_York", "America/Chicago", "America/Phoenix", "America/Los_Angeles", "America/Mexico_City", "America/Anchorage", "Pacific/Honolulu"]
        tz_strings = [F'<option value="{x}" {self.current_choice(opt_dict,"TIMEZONE",x)}>{x}</option>' for x in tz_list]
        tz_string = '\n'.join(tz_strings)
        logger.info(f'tz string {tz_string}')
        page_string = """<html>
         <head></head>
         <body>
           <form method="get" action="save_values">""" + form_string + """
             <label for="timezone"> Choose a Time Zone:</label>
             <select id="timezone" name="TIMEZONE">""" + tz_string + """ </select><p>
             <button type="submit">Submit</button>
             <button type="reset">Reset</button>
           </form>
           <form method="get" action="shutdown">
             <button type="submit">Shutdown</button>
           </form>
         </body>
       </html>"""
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
        outstring = F'<label> {k} <input type="{input_type}" name="{k}" value={v}'
        if type(v) == bool:
            outstring += ' pattern="true|false" title="true or false"> <p>'
        else:
            outstring += '> <p>'
        outstring += '</label>'
        return outstring

    @cherrypy.expose
    def save_values(self, *args, **kwargs):
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
    def shutdown(self, *args, **kwargs):
        cmd = "sudo halt"
        page_string = """<html>
         <head></head>
         <body> Shutting Down <p> Command: """ + cmd + """
         </body>
       </html>"""
        print(F'Shutting Down command {cmd}')
        sleep(parms.sleep_time)
        # os.system(cmd)
        return page_string


def get_ip():
    cmd = "hostname -I"
    ip = subprocess.check_output(cmd, shell=True)
    ip = ip.decode().split(' ')[0]
    return ip


def main(parms):
    ip_address = get_ip()
    cherrypy.config.update({'server.socket_host': ip_address, 'server.socket_port': 9090})
    cherrypy.quickstart(StringGenerator())


for k in parms.__dict__.keys():
    print(F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug == 0:
    main(parms)
    exit(0)
