function myDisplay(elementName,text) {
  document.getElementById(elementName).innerHTML = text;
}

function get_trackstring(tnum) {
  return "track"+((tnum<10)?"0":"")+String(tnum);
}

function get_track(tnum) {
  let trackID = get_trackstring(tnum);
  return document.getElementById(trackID);
}

function play_all_tracks() {
  let t = document.getElementsByTagName("audio");
  var i;
  for (i=0;i<t.length;i++){
    t[i].play();
  }
}
 
let autoplay = true;
let tracknum = 1;
let trackstring = get_trackstring(tracknum);

let current_track = get_track(tracknum);
let next_track = get_track(tracknum + 1);

let timerId = setInterval(show_trackTime, 100, "demo2");

function show_trackTime(elem) { 
  if (current_track == null) { myDisplay(elem, "No Track Playing yet"); return false;
  } else {
    let ctime = current_track.currentTime;
    let tlen = current_track.duration;
    if (ctime >= tlen - 0.15) {
      myDisplay(elem,"Time to play the next track. Track length " + tlen + " current time " + ctime);
      if (autoplay && next_track != null) { advance_track(1,false);}
    } else if ((tlen-ctime)<10) {
      if(next_track==null) { 
        myDisplay(elem,"About to end playback" + tlen + " " + ctime);
        return false;
      } else {
        myDisplay(elem,"Next Track Ready State: " + next_track.readyState);
        if(next_track.readyState < 3) { next_track.load();}
      }
    } else {   
      myDisplay(elem,ctime/tlen);
    }
  }
}
 
function play_track() {
  if (current_track == null) { current_track=get_track(tracknum);} // global var
  if (next_track == null) { next_track=get_track(tracknum+1); }
  if (current_track.paused) {
    current_track.play();
    document.getElementById('pp').innerHTML = "Click here to pause track";} 
  else {
    current_track.pause(); 
    document.getElementById('pp').innerHTML = "Click here to play track";}
}

function advance_track(increment=1,stopping=true) {
  tracknum = tracknum + increment;
  next_track = get_track(tracknum); 
  if (next_track == null){ return false; }
  if (!current_track.paused && stopping) { current_track.pause(); }
  next_track.play();
  current_track = next_track;
  next_track = get_track(tracknum+1)}
 
DOMeventHandler = {
  handleEvent(event) {
    document.getElementById('demo').innerHTML = "Event type " + event.type + " at "+event.currentTarget + "handled at "+Date();
    let track = document.getElementById('track01');
    alert(track.duration);
  }
};
 
// document.addEventListener("click", eventHandler);
// document.addEventListener("DOMContentLoaded", DOMeventHandler);

function showTime() {
  let d = Date();
  myDisplay("demo",d);
}

setInterval(showTime,1000);

