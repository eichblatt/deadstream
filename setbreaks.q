
c:.opts.addopt[`;`debug;1b;"debug"];
c:.opts.addopt[c;`csvpath;`:/home/steve/projects/jerrybase/data/songlist.csv;"file path"];
c:.opts.addopt[c;`csvpath_dc;`:/home/steve/projects/deadstream/dead_and_co_setlists/test.csv;"file path"];
c:.opts.addopt[c;`outpath;`:/home/steve/projects/deadstream/metadata/set_breaks.csv;"output file path"];
parms:.opts.get_opts c;

main:{[parms]
  dc:`date xasc ("DSSSSSS";1#csv) 0:parms`csvpath_dc;            // read the csv file
  dc:`date`event_id xcols dc lj select last event_id by date,act,venue from update event_id:`int$i from select by date,act,venue from dc;
  dc:delete isong from dc;

  jb:("DTISSSSSS";1#csv) 0:parms`csvpath;            // read the csv file
  jb:delete time from jb;

  jb:select from (jb,dc) where not show_set like "Soundcheck*",not show_set like "Session*";
  jb:update isong:1+til count[i] by act from jb;
  jb:update showlen:count[i] by date,event_id from jb;
  jb:update next_set:next show_set by date,event_id from jb;
  jb:jb lj 2!update ievent:i from distinct select date,event_id from jb;
  jb:update song_n:1+til count[i] by ievent,song from jb;   // tail ends of sandwiches, in case of set break errors.


  setbreaks:0!`date`event_id`isong xasc select last song,last song_n,last isong,last next_set by date,event_id,venue,city,state,show_set from jb; / where act like "Grateful*";
  setbreaks:setbreaks lj select Nevents:count distinct event_id by date from setbreaks;
  setbreaks:setbreaks lj 2!select date,event_id,ievent from update ievent:1+til count[i] by date from select by date,event_id from setbreaks where Nevents>1;
  setbreaks:update 1^ievent from setbreaks;
  setbreaks:update break_length:?[next_set=`Encore;`short;`long] from setbreaks;
  .log.info "Writing ",string parms[`outpath] 0: csv 0: 0!setbreaks;
  }


if[not parms[`debug];main[parms];exit 0];
