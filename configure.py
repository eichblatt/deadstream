from timemachine import config
from time import sleep
from threading import Event
import datetime,string,os,optparse,logging,json
import pkg_resources
import cherrypy


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
parser = optparse.OptionParser()
parser.add_option('-d','--debug',dest='debug',type="int",default=1,help="If > 0, don't run the main script on loading [default %default]")
parser.add_option('--options_path',dest='options_path',default=os.path.join(ROOT_DIR,'options.txt'),help="path to options file [default %default]")
parser.add_option('--sleep_time',dest='sleep_time',type="int",default=10,help="how long to sleep before checking network status [default %default]")
parser.add_option('-v','--verbose',dest='verbose',action="store_true",default=False,help="Print more verbose information [default %default]")
parms,remainder = parser.parse_args()

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s: %(name)s %(message)s', level=logging.INFO,datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)


class StringGenerator(object):
    @cherrypy.expose
    def index(self):
        return """<html>
          <head></head>
          <body>
            <form method="get" action="generate">
              <input type="text" value="8" name="length" />
              <button type="submit">Give it now!</button>
            </form>
          </body>
        </html>"""

    @cherrypy.expose
    def generate(self, length=8):
        return ''.join(random.sample(string.hexdigits, int(length)))

def main(parms):
  cherrypy.config.update({'server.socket_host':'192.168.0.21','server.socket_port':9090})
  cherrypy.quickstart(StringGenerator())

for k in parms.__dict__.keys(): print (F"{k:20s} : {parms.__dict__[k]}")
if __name__ == "__main__" and parms.debug==0:
  main(parms)
  exit(0)
