function myFunction() {
  document.getElementById('demo').innerHTML = Date();
}

function get_trackstring(tnum) {
  return "track"+((tnum<10)?"0":"")+String(tnum);
}

function get_track(tnum) {
  let trackID = get_trackstring(tnum);
  return document.getElementById(trackID);
}

let tracknum = 1;
let trackstring = get_trackstring(tracknum);

function pause_track(trackID) {
  let track=document.getElementById(trackID);
  track.pause();
}

function play_track(trackID) {
  let track=document.getElementById(trackID);
  if (track.paused) {
    track.play();
    document.getElementById('pp').innerHTML = "Click here to pause track";} 
  else {
    track.pause(); 
    document.getElementById('pp').innerHTML = "Click here to play track";}
}
function advance_track(increment) {
  let current_track = get_track(tracknum);
  let new_track = get_track(tracknum+increment);
  tracknum = tracknum + increment;
  if (!current_track.paused) { current_track.pause(); }
  new_track.play()}
 
