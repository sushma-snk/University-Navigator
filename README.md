# University Navigator Prototype

A Python + Streamlit prototype with:
- Faculty directory and search
- Timetable-based availability
- Demo campus map
- Illustrative route line and external walking directions
- Faculty timetable entry form
- Sample faculty record creation
- SQLite database created automatically on first run

## Run locally

Python 3.10+ is recommended.

```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Install dependencies and run:
```bash
pip install -r requirements.txt
streamlit run app.py
```

Streamlit will print a local URL, usually http://localhost:8501.

## Prototype behavior

- `university_navigator.db` is created automatically beside `app.py`.
- The database is seeded with illustrative faculty and timetable records only when the faculty table is empty.
- Availability is inferred from timetable entries for the selected date and time.
- “Scheduled free” means no timetable entry is active; it does not prove the faculty member is physically in the office.
- The map uses sample coordinates around a demo center and a straight-line route for illustration.
- The external OpenStreetMap walking-directions link may not align with the demo campus buildings because the coordinates are placeholders.

## Before deployment

1. Replace all sample faculty, contact, schedule, and location records with authorized data.
2. Implement real sign-in and role-based access control. The sidebar role selector is only a demo switch.
3. Validate timetable overlaps, holidays, cancellations, time zones, and faculty schedule updates.
4. Use accurate, approved outdoor coordinates and a routing service that supports the area.
5. Add privacy notices, access logs, backups, and database migration procedures.
6. Configure hosting and data persistence. A local SQLite database is suitable for a prototype, not necessarily for multiple concurrent users on a scaled deployment.
