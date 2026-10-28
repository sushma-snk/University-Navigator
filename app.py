import sqlite3
from datetime import datetime, date, time, timedelta
from urllib.parse import quote
from pathlib import Path

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "university_navigator.db"

st.set_page_config(page_title="University Navigator", page_icon="🧭", layout="wide")

# Demo coordinates only. Replace with approved campus coordinates before deployment.
DEMO_CENTER = (12.9718, 77.5948)
DEMO_LOCATIONS = [
    ("Main Gate", 12.9718, 77.5948),
    ("Academic Block A", 12.9730, 77.5958),
    ("Academic Block B", 12.9707, 77.5961),
    ("Library", 12.9728, 77.5934),
    ("Administration Block", 12.9706, 77.5938),
    ("Student Centre", 12.9735, 77.5945),
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STATUSES = ["In class", "Office hours", "Scheduled free", "No schedule"]


def connect_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faculty_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            designation TEXT NOT NULL DEFAULT 'Faculty',
            email TEXT DEFAULT '',
            office TEXT NOT NULL,
            building TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faculty_id INTEGER NOT NULL,
            weekday TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            activity_title TEXT NOT NULL,
            location TEXT DEFAULT '',
            FOREIGN KEY(faculty_id) REFERENCES faculty(id) ON DELETE CASCADE
        );
        """)
        count = conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
        if count == 0:
            faculty = [
                ("F001", "Dr. A. Kumar", "Computer Science", "Associate Professor", "a.kumar@example.edu", "A-204", "Academic Block A", 12.9730, 77.5958),
                ("F002", "Dr. B. Sharma", "Electronics", "Assistant Professor", "b.sharma@example.edu", "B-116", "Academic Block B", 12.9707, 77.5961),
                ("F003", "Dr. C. Rao", "Mathematics", "Professor", "c.rao@example.edu", "A-310", "Academic Block A", 12.9730, 77.5958),
                ("F004", "Ms. D. Nair", "Design", "Assistant Professor", "d.nair@example.edu", "S-105", "Student Centre", 12.9735, 77.5945),
                ("F005", "Mr. E. Joseph", "Administration", "Coordinator", "e.joseph@example.edu", "AD-12", "Administration Block", 12.9706, 77.5938),
            ]
            conn.executemany("""
                INSERT INTO faculty
                (faculty_code, name, department, designation, email, office, building, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, faculty)
            fid = {row["faculty_code"]: row["id"] for row in conn.execute("SELECT id, faculty_code FROM faculty")}
            sample_schedule = [
                ("F001", "Monday", "09:00", "10:00", "Class", "Machine Learning", "Academic Block A"),
                ("F001", "Monday", "11:00", "12:00", "Office hours", "Student consultation", "A-204"),
                ("F001", "Wednesday", "14:00", "15:00", "Class", "Artificial Intelligence", "Academic Block A"),
                ("F002", "Monday", "10:00", "11:00", "Class", "Digital Systems", "Academic Block B"),
                ("F002", "Tuesday", "13:00", "14:00", "Office hours", "Project guidance", "B-116"),
                ("F003", "Tuesday", "09:00", "10:00", "Class", "Engineering Mathematics", "Academic Block A"),
                ("F003", "Thursday", "11:00", "12:00", "Office hours", "Student consultation", "A-310"),
                ("F004", "Friday", "14:00", "15:00", "Class", "Design Studio", "Student Centre"),
                ("F005", "Monday", "12:00", "13:00", "Office hours", "Student services", "AD-12"),
            ]
            conn.executemany("""
                INSERT INTO timetable
                (faculty_id, weekday, start_time, end_time, activity_type, activity_title, location)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [(fid[code], day, start, end, typ, title, loc) for code, day, start, end, typ, title, loc in sample_schedule])


def get_faculty(active_only=True):
    with connect_db() as conn:
        q = "SELECT * FROM faculty"
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY name"
        return pd.read_sql_query(q, conn)


def get_schedule(faculty_id=None):
    with connect_db() as conn:
        q = """SELECT t.*, f.name AS faculty_name, f.faculty_code
               FROM timetable t JOIN faculty f ON f.id=t.faculty_id"""
        params = ()
        if faculty_id is not None:
            q += " WHERE t.faculty_id=?"
            params = (int(faculty_id),)
        q += " ORDER BY t.weekday, t.start_time"
        return pd.read_sql_query(q, conn, params=params)


def get_availability(faculty_id, at_dt):
    weekday = at_dt.strftime("%A")
    now_str = at_dt.strftime("%H:%M")
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT * FROM timetable
            WHERE faculty_id=? AND weekday=?
            ORDER BY start_time
        """, (int(faculty_id), weekday)).fetchall()

    current = [r for r in rows if r["start_time"] <= now_str < r["end_time"]]
    if current:
        item = current[0]
        if item["activity_type"] == "Office hours":
            status = "Office hours"
        else:
            status = "In class"
        detail = f'{item["activity_title"]} · {item["start_time"]}–{item["end_time"]} · {item["location"] or "Location not specified"}'
    elif rows:
        status = "Scheduled free"
        future = [r for r in rows if r["start_time"] > now_str]
        if future:
            item = future[0]
            detail = f'Next: {item["activity_title"]} at {item["start_time"]} ({item["location"] or "location not specified"})'
        else:
            detail = "No further activities listed for today."
    else:
        status = "No schedule"
        detail = "No timetable entries are available for this weekday."
    return status, detail


def add_timetable_entry(faculty_id, weekday, start_time, end_time, activity_type, activity_title, location):
    if start_time >= end_time:
        raise ValueError("End time must be later than start time.")
    with connect_db() as conn:
        overlap = conn.execute("""
            SELECT COUNT(*) FROM timetable
            WHERE faculty_id=? AND weekday=?
              AND start_time < ? AND end_time > ?
        """, (int(faculty_id), weekday, end_time, start_time)).fetchone()[0]
        if overlap:
            raise ValueError("This entry overlaps an existing timetable entry for this faculty member.")
        conn.execute("""
            INSERT INTO timetable
            (faculty_id, weekday, start_time, end_time, activity_type, activity_title, location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (int(faculty_id), weekday, start_time, end_time, activity_type, activity_title, location))


init_db()
faculty_df = get_faculty()

st.title("🧭 University Navigator")
st.caption("Prototype · Python + Streamlit · Demo campus data")
st.info("Demo mode: names, schedules, coordinates, and contact details are sample data. Availability reflects the timetable only, not confirmed physical presence.")

with st.sidebar:
    st.header("Navigator")
    page = st.radio("Go to", ["Find faculty & navigate", "Timetable", "Manage data"])
    st.divider()
    st.caption("Prototype role selector")
    role = st.selectbox("View as", ["Student / Visitor", "Faculty", "Administrator"])
    st.caption("Role selection is for demonstration only; it is not authentication.")

if page == "Find faculty & navigate":
    st.subheader("Find a faculty member")
    if faculty_df.empty:
        st.warning("No active faculty records are available.")
        st.stop()

    left, right = st.columns([0.9, 1.3], gap="large")
    with left:
        query = st.text_input("Search by name, department, designation, or office", placeholder="e.g., Kumar or Computer Science")
        depts = ["All departments"] + sorted(faculty_df["department"].dropna().unique().tolist())
        dept = st.selectbox("Department", depts)
        filtered = faculty_df.copy()
        if query.strip():
            q = query.strip().lower()
            cols = ["name", "department", "designation", "office", "building", "faculty_code"]
            mask = filtered[cols].fillna("").astype(str).apply(lambda col: col.str.lower().str.contains(q, regex=False)).any(axis=1)
            filtered = filtered[mask]
        if dept != "All departments":
            filtered = filtered[filtered["department"] == dept]

        if filtered.empty:
            st.warning("No faculty members match your search.")
            st.stop()

        options = {f'{r["name"]} — {r["department"]} ({r["office"]})': int(r["id"]) for _, r in filtered.iterrows()}
        selected_label = st.selectbox("Select faculty", list(options.keys()))
        selected_id = options[selected_label]
        selected = faculty_df[faculty_df["id"] == selected_id].iloc[0]

        use_custom_time = st.checkbox("Test availability at a different date/time")
        if use_custom_time:
            check_date = st.date_input("Date", value=date.today())
            check_time = st.time_input("Time", value=datetime.now().replace(second=0, microsecond=0).time())
            check_dt = datetime.combine(check_date, check_time)
        else:
            check_dt = datetime.now()

        status, detail = get_availability(selected_id, check_dt)
        st.markdown("### Faculty profile")
        st.write(f'**{selected["name"]}**')
        st.write(f'{selected["designation"]} · {selected["department"]}')
        st.write(f'Office: {selected["office"]}, {selected["building"]}')
        st.write(f'Email: {selected["email"] or "Not provided"}')
        color = {"In class": "🔴", "Office hours": "🟢", "Scheduled free": "🟡", "No schedule": "⚪"}.get(status, "⚪")
        st.markdown(f"### {color} {status}")
        st.write(detail)
        st.caption(f"Schedule checked for {check_dt.strftime('%A, %d %b %Y at %H:%M')}.")

        st.markdown("### Navigate")
        start_names = [x[0] for x in DEMO_LOCATIONS]
        start_name = st.selectbox("Starting point", start_names, index=0)
        start = next((x for x in DEMO_LOCATIONS if x[0] == start_name), DEMO_LOCATIONS[0])
        destination = (selected["building"], float(selected["latitude"]), float(selected["longitude"]))
        directions_url = (
            "https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot"
            f"&route={start[1]}%2C{start[2]}%3B{destination[1]}%2C{destination[2]}"
        )
        st.link_button("Open walking directions", directions_url, use_container_width=True)
        st.caption("The demo map shows a straight-line guide, not a verified pedestrian route.")

    with right:
        st.subheader("Demo campus map")
        m = folium.Map(location=DEMO_CENTER, zoom_start=16, control_scale=True, tiles="OpenStreetMap")
        for name, lat, lon in DEMO_LOCATIONS:
            folium.Marker([lat, lon], tooltip=name, popup=name, icon=folium.Icon(color="blue", icon="building", prefix="fa")).add_to(m)

        start_names = [x[0] for x in DEMO_LOCATIONS]
        start = next((x for x in DEMO_LOCATIONS if x[0] == start_name), DEMO_LOCATIONS[0])
        dest = (selected["building"], float(selected["latitude"]), float(selected["longitude"]))
        folium.Marker([dest[1], dest[2]], tooltip=f'{selected["name"]} — {selected["office"]}',
                      popup=f'{selected["name"]}<br>{selected["office"]}',
                      icon=folium.Icon(color="green", icon="user", prefix="fa")).add_to(m)
        folium.Marker([start[1], start[2]], tooltip="Starting point", icon=folium.Icon(color="red", icon="play", prefix="fa")).add_to(m)
        folium.PolyLine([[start[1], start[2]], [dest[1], dest[2]]], color="green", weight=4, dash_array="8, 8",
                        tooltip="Illustrative demo route").add_to(m)
        st_folium(m, height=560, use_container_width=True, returned_objects=[])

        st.markdown("**Selected destination**")
        st.write(f'{selected["building"]} · Office {selected["office"]}')
        st.caption(f'Demo coordinates: {dest[1]:.5f}, {dest[2]:.5f}')

elif page == "Timetable":
    st.subheader("Faculty timetable")
    all_faculty = get_faculty()
    if all_faculty.empty:
        st.warning("No faculty records found.")
    else:
        labels = {f'{r["name"]} — {r["department"]}': int(r["id"]) for _, r in all_faculty.iterrows()}
        chosen = st.selectbox("Choose faculty", list(labels.keys()))
        schedule = get_schedule(labels[chosen])
        if schedule.empty:
            st.info("No timetable entries yet.")
        else:
            schedule = schedule[["weekday", "start_time", "end_time", "activity_type", "activity_title", "location"]]
            schedule.columns = ["Day", "Start", "End", "Type", "Activity", "Location"]
            st.dataframe(schedule, hide_index=True, use_container_width=True)
        if role in ["Faculty", "Administrator"]:
            st.markdown("### Add timetable entry")
            with st.form("add_schedule"):
                day = st.selectbox("Weekday", WEEKDAYS)
                start_t = st.time_input("Start time", value=time(9, 0), key="sched_start")
                end_t = st.time_input("End time", value=time(10, 0), key="sched_end")
                activity_type = st.selectbox("Activity type", ["Class", "Office hours", "Meeting", "Other"])
                title = st.text_input("Activity title", placeholder="e.g., Student consultation")
                location = st.text_input("Activity location", placeholder="e.g., A-204")
                submitted = st.form_submit_button("Add timetable entry")
            if submitted:
                try:
                    if not title.strip():
                        raise ValueError("Please enter an activity title.")
                    add_timetable_entry(labels[chosen], day, start_t.strftime("%H:%M"), end_t.strftime("%H:%M"),
                                        activity_type, title.strip(), location.strip())
                    st.success("Timetable entry added.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        else:
            st.caption("Switch to the Faculty or Administrator demo view to try adding an entry. This selector is not secure authentication.")

elif page == "Manage data":
    st.subheader("Manage faculty records")
    st.caption("Sample admin controls for prototyping. Do not expose this page publicly without real authentication and authorization.")
    all_faculty = get_faculty(active_only=False)
    st.dataframe(all_faculty[["faculty_code", "name", "department", "designation", "office", "building", "active"]],
                 hide_index=True, use_container_width=True)

    if role == "Administrator":
        st.markdown("### Add a faculty member")
        with st.form("add_faculty"):
            code = st.text_input("Faculty code", placeholder="F006")
            name = st.text_input("Full name")
            department = st.text_input("Department")
            designation = st.text_input("Designation", value="Faculty")
            email = st.text_input("Email")
            office = st.text_input("Office / room", placeholder="C-101")
            building = st.selectbox("Building", [x[0] for x in DEMO_LOCATIONS if x[0] != "Main Gate"])
            building_loc = next(x for x in DEMO_LOCATIONS if x[0] == building)
            lat = st.number_input("Demo latitude", value=float(building_loc[1]), format="%.6f")
            lon = st.number_input("Demo longitude", value=float(building_loc[2]), format="%.6f")
            submitted = st.form_submit_button("Add faculty")
        if submitted:
            try:
                if not all([code.strip(), name.strip(), department.strip(), office.strip()]):
                    raise ValueError("Faculty code, name, department, and office are required.")
                with connect_db() as conn:
                    conn.execute("""
                        INSERT INTO faculty
                        (faculty_code, name, department, designation, email, office, building, latitude, longitude)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (code.strip(), name.strip(), department.strip(), designation.strip(), email.strip(),
                          office.strip(), building, lat, lon))
                st.success("Faculty member added.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("That faculty code already exists.")
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.info("Switch the prototype role to Administrator to test adding faculty records.")

st.divider()
st.caption("University Navigator prototype · Replace demo records and coordinates with approved university data before real deployment.")
