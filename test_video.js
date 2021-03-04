const http = require('http');
//var video = require('!style-loader!css-loader!./node_modules/video.js/dist/video.css')
var video = require('./node_modules/video.js/dist/video.js')

const hostname = '127.0.0.1';
const port = 3001;

const server = http.createServer((req, res) => {
  res.statusCode = 200;
  res.setHeader('Content-Type', 'text/plain');
  res.end('Hello World');
});

server.listen(port, hostname, () => {
  console.log(`Server running at http://${hostname}:${port}/`);
});

