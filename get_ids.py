import requests
import json
import os

url_endpoint = 'https://archive.org/services/search/v1/scrape'
parms = {'debug':'false','xvar':'production','total_only':'false','count':'10000','sorts':'date asc,avg_rating desc,num_favorites desc,downloads desc','fields':'identifier,date,avg_rating,num_reviews,num_favorites,stars,downloads,files_count,format,collection,source,subject,type'}

def get_ids(year,parms=parms,prev_rows=0):
  query = 'collection:GratefulDead AND year:'+str(year)
  parms['q'] = query
  r = requests.get(url_endpoint,params=parms)
  print("url is {}".format(r.url))
  if r.status_code != 200: print ("error collecting year {}".format(year)); raise Exception('Download','Error {} collection year {}'.format(r.status_code,year))
  j = r.json()
  current_rows = prev_rows + j['count']
  if current_rows != j['total']:  
    print ("there are {} some missing rows in year {}".format(j['total']-current_rows,year))
  #  parms['cursor'] = j['cursor']
  #  parms.pop('q')
  #  get_ids(year,parms,prev_rows=current_rows) 
  return r.json()

for year in range(1965,1996,1):
  ids = get_ids(year) 
  pathname = os.path.join(os.getenv('HOME'),'projects','dead_vault','data',str(year),'ids.json')
  os.makedirs(os.path.dirname(pathname),exist_ok=True)
  json.dump(ids,open(pathname,'w'))
