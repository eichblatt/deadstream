from deadstream import controls as c
import datetime

d = '1977-05-08'
d =  datetime.date(*(int(s) for s in d.split('-')))

s = c.screen()
s.clear()

s.show_staged_date(d)

d2 = '1979-11-02'
d2 =  datetime.date(*(int(s) for s in d2.split('-')))
s.show_selected_date(d2)

s.show_text("Venue",(0,30))
for i in [d,d2,d,d2,d,d2,d,d2,d,d2]: s.show_staged_date(i)
for i in [d,d2,d,d2,d,d2,d,d2,d,d2]: s.show_selected_date(i)

