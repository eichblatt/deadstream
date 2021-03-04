const http = require('http');
const url = require('url');
var fs = require('fs');
var video = require('video');

const hostname = '127.0.0.1';
const port = 3000;

var dt = require('./my_module');

const server = http.createServer((req, res) => {
  res.statusCode = 200;
  res.setHeader('Content-Type', 'text/plain');
  res.write('The Date and time are currently: '+ dt.myDateTime());
  var q = url.parse(req.url, true).query;
  var txt = q.year + " " + q.month;
  res.write('The URL request is ' + req.url);
  res.end(txt);
});

server.listen(port, hostname, () => {
  console.log(`Server running at http://${hostname}:${port}/`);
});

