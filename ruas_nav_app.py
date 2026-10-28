import sqlite3
from pathlib import Path
from datetime import datetime, date, time
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

DB_PATH = Path(__file__).with_name('ruas_navigator.db')
st.set_page_config(page_title='RUAS Peenya Navigator', page_icon='🧭', layout='wide')

# DEMO coordinates and labels only. Replace with verified campus survey data.
LOCATIONS = [
    ('Demo Gate 1', 13.03200, 77.51600, 'Gate'),
    ('Demo Gate 2', 13.03235, 77.51665, 'Gate'),
    ('Demo Gate 3', 13.03155, 77.51670, 'Gate'),
    ('Engineering Block', 13.03215, 77.51635, 'Block'),
    ('Design Block', 13.03185, 77.51680, 'Block'),
    ('Central Admin Block', 13.03175, 77.51625, 'Block'),
    ('Library', 13.03245, 77.51635, 'Facility'),
]
CENTER = (13.0320, 77.51645)
DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
ACTIVITY_TYPES = ['Class','Office hours','Meeting','Other']
ATTENDANCE_STATES = ['Present','Absent','On duty','Not marked']
DEPARTMENTS = [
    'Aerospace Engineering','Artificial Intelligence and Machine Learning',
    'Automotive and Robotics Engineering','Civil Engineering','Computer Science and Engineering',
    'Electrical and Electronics Engineering','Electronics and Communication Engineering',
    'Information Science and Engineering','Mathematics and Computing','Mechanical Engineering',
    'Robotics Engineering','Art and Design','Natural Sciences','Other / To be confirmed'
]

def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS departments(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS faculty(
          id INTEGER PRIMARY KEY, faculty_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
          department_id INTEGER NOT NULL, designation TEXT DEFAULT '', email TEXT DEFAULT '',
          office TEXT DEFAULT '', block TEXT DEFAULT '', latitude REAL, longitude REAL, active INTEGER DEFAULT 1,
          FOREIGN KEY(department_id) REFERENCES departments(id));
        CREATE TABLE IF NOT EXISTS timetable(
          id INTEGER PRIMARY KEY, faculty_id INTEGER NOT NULL, weekday TEXT NOT NULL,
          start_time TEXT NOT NULL, end_time TEXT NOT NULL, activity_type TEXT NOT NULL,
          activity_title TEXT NOT NULL, location TEXT DEFAULT '',
          FOREIGN KEY(faculty_id) REFERENCES faculty(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS attendance_register(
          id INTEGER PRIMARY KEY, faculty_id INTEGER NOT NULL, attendance_date TEXT NOT NULL,
          attendance_status TEXT NOT NULL, marked_at TEXT NOT NULL, marked_by TEXT DEFAULT '', note TEXT DEFAULT '',
          UNIQUE(faculty_id, attendance_date), FOREIGN KEY(faculty_id) REFERENCES faculty(id) ON DELETE CASCADE);
        ''')
        for d in DEPARTMENTS:
            c.execute('INSERT OR IGNORE INTO departments(name) VALUES(?)',(d,))
        if c.execute('SELECT COUNT(*) FROM faculty').fetchone()[0] == 0:
            did = {r['name']:r['id'] for r in c.execute('SELECT id,name FROM departments')}
            demo = [
              ('DEMO001','Dr. A. Kumar','Computer Science and Engineering','Associate Professor','demo.kumar@example.edu','E-204','Engineering Block',13.03215,77.51635),
              ('DEMO002','Dr. B. Sharma','Electronics and Communication Engineering','Assistant Professor','demo.sharma@example.edu','E-116','Engineering Block',13.03215,77.51635),
              ('DEMO003','Dr. C. Rao','Mathematics and Computing','Professor','demo.rao@example.edu','E-310','Engineering Block',13.03215,77.51635),
              ('DEMO004','Ms. D. Nair','Art and Design','Assistant Professor','demo.nair@example.edu','D-105','Design Block',13.03185,77.51680),
              ('DEMO005','Dr. E. Iyer','Artificial Intelligence and Machine Learning','Assistant Professor','demo.iyer@example.edu','E-212','Engineering Block',13.03215,77.51635)]
            for code,name,dept,desig,email,office,block,lat,lon in demo:
                c.execute('INSERT INTO faculty(faculty_code,name,department_id,designation,email,office,block,latitude,longitude) VALUES(?,?,?,?,?,?,?,?,?)',
                          (code,name,did[dept],desig,email,office,block,lat,lon))
            fids = {r['faculty_code']:r['id'] for r in c.execute('SELECT id,faculty_code FROM faculty')}
            rows = [
              ('DEMO001','Monday','09:00','10:00','Class','Machine Learning','Engineering Block'),
              ('DEMO001','Monday','11:00','12:00','Office hours','Student consultation','E-204'),
              ('DEMO001','Wednesday','14:00','15:00','Class','Artificial Intelligence','Engineering Block'),
              ('DEMO002','Monday','10:00','11:00','Class','Digital Systems','Engineering Block'),
              ('DEMO002','Tuesday','13:00','14:00','Office hours','Project guidance','E-116'),
              ('DEMO003','Tuesday','09:00','10:00','Class','Engineering Mathematics','Engineering Block'),
              ('DEMO003','Thursday','11:00','12:00','Office hours','Student consultation','E-310'),
              ('DEMO004','Friday','14:00','15:00','Class','Design Studio','Design Block'),
              ('DEMO005','Wednesday','10:00','11:00','Class','Applied AI','Engineering Block')]
            c.executemany('INSERT INTO timetable(faculty_id,weekday,start_time,end_time,activity_type,activity_title,location) VALUES(?,?,?,?,?,?,?)',
                          [(fids[x[0]],*x[1:]) for x in rows])

def departments():
    with db() as c: return pd.read_sql_query('SELECT * FROM departments WHERE active=1 ORDER BY name',c)

def faculty(dept_id=None, active=True):
    q='SELECT f.*,d.name AS department FROM faculty f JOIN departments d ON d.id=f.department_id'
    wh=[]; args=[]
    if active: wh.append('f.active=1')
    if dept_id is not None: wh.append('f.department_id=?'); args.append(int(dept_id))
    if wh: q+=' WHERE '+' AND '.join(wh)
    q+=' ORDER BY f.name'
    with db() as c: return pd.read_sql_query(q,c,params=args)

def schedule(fid):
    with db() as c:
        return pd.read_sql_query('''SELECT weekday,start_time,end_time,activity_type,activity_title,location FROM timetable WHERE faculty_id=? ORDER BY weekday,start_time''',c,params=(int(fid),))

def check_availability(fid, dt):
    with db() as c:
        att=c.execute('SELECT * FROM attendance_register WHERE faculty_id=? AND attendance_date=?',(int(fid),dt.date().isoformat())).fetchone()
        entries=c.execute('SELECT * FROM timetable WHERE faculty_id=? AND weekday=? ORDER BY start_time',(int(fid),dt.strftime('%A'))).fetchall()
    if att and att['attendance_status']=='Absent':
        return 'Marked absent', f"Attendance register says Absent (updated {att['marked_at']}). Timetable is reference only.", att
    att_msg=(f"Attendance register: {att['attendance_status']} (marked {att['marked_at']})." if att else 'No attendance entry recorded for this date.')
    now=dt.strftime('%H:%M')
    active=[x for x in entries if x['start_time']<=now<x['end_time']]
    if active:
        x=active[0]
        status='Office hours scheduled' if x['activity_type']=='Office hours' else ('In class (timetable)' if x['activity_type']=='Class' else f"{x['activity_type']} scheduled")
        return status, f"{x['activity_title']} · {x['start_time']}–{x['end_time']} · {x['location'] or 'location not specified'}. {att_msg}", att
    future=[x for x in entries if x['start_time']>now]
    next_msg=f"Next scheduled: {future[0]['activity_title']} at {future[0]['start_time']} ({future[0]['location'] or 'location not specified'})." if future else ('No further activities listed today.' if entries else 'No timetable entries for this weekday.')
    return ('Scheduled free' if entries else 'No timetable'), f'{next_msg} {att_msg} A free timetable slot does not confirm physical presence.', att

def add_schedule(fid, day, start, end, typ, title, loc):
    if start>=end: raise ValueError('End time must be later than start time.')
    with db() as c:
        n=c.execute('SELECT COUNT(*) FROM timetable WHERE faculty_id=? AND weekday=? AND start_time<? AND end_time>?',(int(fid),day,end,start)).fetchone()[0]
        if n: raise ValueError('This entry overlaps an existing timetable entry.')
        c.execute('INSERT INTO timetable(faculty_id,weekday,start_time,end_time,activity_type,activity_title,location) VALUES(?,?,?,?,?,?,?)',(int(fid),day,start,end,typ,title,loc))

init_db()
dep_df=departments()
st.title('🧭 RUAS Peenya Campus Navigator')
st.caption('Department-first faculty search · Timetable and attendance · Campus navigation')
st.warning('DEMO MODE: faculty, timetable, attendance, gates, blocks and coordinates are illustrative. This is not an official campus map.')
with st.sidebar:
    page=st.radio('Open page',['Find faculty & navigate','Timetable','Attendance register','Admin: faculty records'])
    role=st.selectbox('Prototype role',['Student / Visitor','Faculty','Administrator'])
    st.caption('Demo role selector only; not authentication.')

if page=='Find faculty & navigate':
    st.subheader('1. Select department')
    dept_ids={r['name']:int(r['id']) for _,r in dep_df.iterrows()}
    dept_name=st.selectbox('Department',list(dept_ids))
    fdf=faculty(dept_ids[dept_name])
    st.subheader('2. Select faculty')
    if fdf.empty: st.info('No faculty records in this department yet.'); st.stop()
    q=st.text_input('Filter faculty in selected department',placeholder='Name, designation, or office')
    if q.strip():
        term=q.lower().strip(); fdf=fdf[fdf.apply(lambda r:any(term in str(r[c]).lower() for c in ['name','designation','office','block']),axis=1)]
    if fdf.empty: st.warning('No matching faculty.'); st.stop()
    opts={f"{r['name']} · {r['designation']} · Office {r['office'] or 'not entered'}":int(r['id']) for _,r in fdf.iterrows()}
    label=st.selectbox('Faculty list',list(opts)); fid=opts[label]; person=fdf[fdf.id==fid].iloc[0]
    st.subheader('3. Check availability')
    custom=st.checkbox('Test a different date/time')
    if custom:
        d=st.date_input('Date',date.today()); t=st.time_input('Time',datetime.now().replace(second=0,microsecond=0).time()); dt=datetime.combine(d,t)
    else: dt=datetime.now()
    status,detail,att=check_availability(fid,dt)
    c1,c2=st.columns([1,2])
    with c1:
        st.markdown(f'### {status}'); st.write(f"**{person['name']}**"); st.write(f"{person['designation']} · {person['department']}")
        st.write(f"Office: {person['office'] or 'Not entered'}"); st.write(f"Block: {person['block'] or 'Not entered'}")
        if person['email']: st.write(f"Email: {person['email']}")
    with c2:
        st.info(detail)
        if att: st.caption(f"Attendance: {att['attendance_status']} · {att['marked_at']} · Marked by {att['marked_by'] or 'not specified'}")
        else: st.caption('Attendance register has no entry for this date; missing does not mean absent.')
    st.subheader('4. Navigate from a gate or block')
    starts=[f'{x[0]} ({x[3]})' for x in LOCATIONS]
    start_label=st.selectbox('Starting point',starts)
    start_name=start_label.rsplit(' (',1)[0]; start=next(x for x in LOCATIONS if x[0]==start_name)
    dest_lat=float(person.latitude) if pd.notna(person.latitude) else CENTER[0]
    dest_lon=float(person.longitude) if pd.notna(person.longitude) else CENTER[1]
    m=folium.Map(location=CENTER,zoom_start=17,control_scale=True,tiles='OpenStreetMap')
    for name,lat,lon,kind in LOCATIONS:
        color='red' if kind=='Gate' else ('purple' if kind=='Facility' else 'blue')
        folium.Marker([lat,lon],tooltip=f'{name} · {kind}',popup=name,icon=folium.Icon(color=color,icon='map-marker',prefix='fa')).add_to(m)
    folium.Marker([dest_lat,dest_lon],tooltip=f"{person['name']} · Office {person['office']}",popup=f"{person['name']}<br>{person['office']}",icon=folium.Icon(color='green',icon='user',prefix='fa')).add_to(m)
    folium.Marker([start[1],start[2]],tooltip='Starting point',icon=folium.Icon(color='orange',icon='play',prefix='fa')).add_to(m)
    folium.PolyLine([[start[1],start[2]],[dest_lat,dest_lon]],color='green',weight=4,dash_array='7,8',tooltip='Illustrative route').add_to(m)
    st_folium(m,height=510,use_container_width=True,returned_objects=[])
    url=f"https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&route={start[1]}%2C{start[2]}%3B{dest_lat}%2C{dest_lon}"
    st.link_button('Open walking directions',url)
    st.caption('The line on this demo map is not a verified walkway. External directions may not match the placeholder campus points.')
    st.markdown('#### Timetable')
    s=schedule(fid)
    if s.empty: st.caption('No timetable entries yet.')
    else: st.dataframe(s,hide_index=True,use_container_width=True)

elif page=='Timetable':
    fdf=faculty()
    if fdf.empty: st.info('No faculty records.'); st.stop()
    opts={f"{r['name']} · {r['department']}":int(r.id) for _,r in fdf.iterrows()}
    chosen=st.selectbox('Faculty member',list(opts)); st.dataframe(schedule(opts[chosen]),hide_index=True,use_container_width=True)
    if role in ['Faculty','Administrator']:
        with st.form('add_schedule'):
            day=st.selectbox('Day',DAYS); start=st.time_input('Start',time(9,0)); end=st.time_input('End',time(10,0)); typ=st.selectbox('Type',ACTIVITY_TYPES); title=st.text_input('Activity title'); loc=st.text_input('Room/location'); submit=st.form_submit_button('Add timetable entry')
        if submit:
            try:
                if not title.strip(): raise ValueError('Activity title is required.')
                add_schedule(opts[chosen],day,start.strftime('%H:%M'),end.strftime('%H:%M'),typ,title.strip(),loc.strip()); st.success('Saved.'); st.rerun()
            except ValueError as e: st.error(str(e))

elif page=='Attendance register':
    st.subheader('Attendance register')
    st.caption('Manual demo entry only. Connect an approved official export for production; never infer absence from a missing entry.')
    fdf=faculty(); opts={f"{r['name']} · {r['department']}":int(r.id) for _,r in fdf.iterrows()}
    with st.form('attendance'):
        chosen=st.selectbox('Faculty member',list(opts)); adate=st.date_input('Date',date.today()); status=st.selectbox('Attendance status',ATTENDANCE_STATES); by=st.text_input('Marked by'); note=st.text_input('Note'); submit=st.form_submit_button('Save attendance')
    if submit:
        if role not in ['Faculty','Administrator']: st.error('Switch to Faculty or Administrator demo role to test entry. Real use needs authentication.')
        else:
            with db() as c:
                c.execute('''INSERT INTO attendance_register(faculty_id,attendance_date,attendance_status,marked_at,marked_by,note) VALUES(?,?,?,?,?,?) ON CONFLICT(faculty_id,attendance_date) DO UPDATE SET attendance_status=excluded.attendance_status,marked_at=excluded.marked_at,marked_by=excluded.marked_by,note=excluded.note''',(opts[chosen],adate.isoformat(),status,datetime.now().isoformat(timespec='minutes'),by,note))
            st.success('Attendance saved.'); st.rerun()
    with db() as c:
        attdf=pd.read_sql_query('''SELECT f.name,d.name AS department,a.attendance_date,a.attendance_status,a.marked_at,a.marked_by,a.note FROM attendance_register a JOIN faculty f ON f.id=a.faculty_id JOIN departments d ON d.id=f.department_id ORDER BY a.attendance_date DESC,f.name''',c)
    if attdf.empty: st.info('No attendance records entered yet.')
    else: st.dataframe(attdf,hide_index=True,use_container_width=True)

else:
    st.subheader('Admin: faculty records')
    st.caption('Department options are provisional and must be verified for the Peenya campus.')
    st.dataframe(dep_df[['name','active']],hide_index=True,use_container_width=True)
    allf=faculty(active=False)
    st.dataframe(allf[['faculty_code','name','department','designation','office','block','active']],hide_index=True,use_container_width=True)
    if role=='Administrator':
        dept_ids={r['name']:int(r['id']) for _,r in dep_df.iterrows()}
        with st.form('new_faculty'):
            code=st.text_input('Faculty code'); name=st.text_input('Faculty name'); dept=st.selectbox('Department',list(dept_ids)); designation=st.text_input('Designation',value='Faculty'); email=st.text_input('Email'); office=st.text_input('Office/room'); block=st.selectbox('Demo block',[x[0] for x in LOCATIONS if x[3]=='Block']); loc=next(x for x in LOCATIONS if x[0]==block); lat=st.number_input('Demo latitude',value=float(loc[1]),format='%.6f'); lon=st.number_input('Demo longitude',value=float(loc[2]),format='%.6f'); submit=st.form_submit_button('Add faculty')
        if submit:
            try:
                if not code.strip() or not name.strip() or not office.strip(): raise ValueError('Faculty code, name and office are required.')
                with db() as c: c.execute('INSERT INTO faculty(faculty_code,name,department_id,designation,email,office,block,latitude,longitude) VALUES(?,?,?,?,?,?,?,?,?)',(code.strip(),name.strip(),dept_ids[dept],designation.strip(),email.strip(),office.strip(),block,lat,lon))
                st.success('Faculty added.'); st.rerun()
            except sqlite3.IntegrityError: st.error('Faculty code already exists.')
            except ValueError as e: st.error(str(e))
    else: st.info('Switch to Administrator demo role to test adding faculty.')

st.divider()
st.caption('RUAS Peenya Navigator prototype · Replace demo records, gate names, block names and coordinates with verified campus data before real use.')
