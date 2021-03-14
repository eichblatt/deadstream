import optparse
import sys,os,os.path
import GD

parser = optparse.OptionParser()
parser.add_option('--dbpath',dest='dbpath',default=os.path.join(os.getenv('HOME'),'projects/dead_vault/metadata'))
parser.add_option('--reload_ids',dest='reload_ids',default=False)
parser.add_option('--verbose',dest='verbose',default=False)
parser.add_option('--debug',dest='debug',default=True)

parms,remainder = parser.parse_args()

def main(parms):
  a = GD.GDArchive(parms.dbpath)
  tapes = []
  for t in a.ids[:8000]: 
     tapes.append(GD.GDTape(parms.dbpath,t)) 
  datelist = GD.GDDateList(tapes)
  
if (not parms.debug) and __name__ == "__main__":
   main(parms)


