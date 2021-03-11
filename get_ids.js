
const fs = require('fs');
const https = require('https');

let start=1966;
let end = 1966;

total_result = {};
function id_promise(year){
let URL = 'https://archive.org/services/search/v1/scrape?debug=false&xvar=production&total_only=false&count=1000&fields=identifier%2Cdate%2Cnum_reviews%2Cnum_favorites%2Cfiles_count%2Cavg_rating&q=collection%3AGratefulDead AND year%3A' + year;
  return new Promise((resolve,reject) => {
    console.log ("URL is "+URL);
    https.get(URL,(resp)=> {
      let data = [];
      resp.on('data',(chunk)=> { data.push(chunk);});
      resp.on('end',()=> { 
         console.log("Total Items Fetched: " + JSON.parse(data).total); 
         total_result[year] = Buffer.concat(data).toString();
         resolve(total_result[year]);
      });
     }).on("error",(err)=> {reject(err);});
 });
}

function new_get_ids(year){
  let resp = id_promise(year).then(
     result => console.log("Success "+year),
     error => console.log(error));
}

function request_identifiers(year){
  let URL = 'https://archive.org/services/search/v1/scrape?debug=false&xvar=production&total_only=false&count=1000&fields=identifier%2Cdate%2Cnum_reviews%2Cnum_favorites%2Cfiles_count%2Cavg_rating&q=collection%3AGratefulDead AND year%3A' + year;
  console.log ("URL is "+URL);
  let data = '';
  https.get(URL,(resp)=> {
    resp.on('data',(chunk)=> { data += chunk;});
    resp.on('end',()=> { 
       console.log("Total Items Fetched: " + JSON.parse(data).total); 
       return data});
   }).on("error",(err)=> {console.log("Error: "+err.message);});
}
/*
let id_dict = {};
for (let year=start; year<end+1; year++){
  console.log ("year is " + year);
  id_dict[year] = request_identifiers(year);
};

fs.writeFile('/home/steve/projects/dead_vault/data',JSON.stringify(id_dict));
*/
