import optparse
import sys,os,os.path
import GD

parser = optparse.OptionParser()
parser.add_option('--dbpath',dest='dbpath',default=os.path.join(os.getenv('HOME'),'projects/dead_vault/data'))
parser.add_option('--force_reload',dest='force_reload',default=False)
parser.add_option('--verbose',dest='verbose',default=False)
parser.add_option('--debug',dest='debug',default=True)

parms,remainder = parser.parse_args()

def main(parms):
  a = GD.GDArchive(parms.dbpath,force_reload=parms.force_reload)
  tapes = []
  for t in a.ids[10000:10100]: 
     tapes.append(GD.GDTape(t)) 

if (not parms.debug) and __name__ == "__main__":
   main(parms)


