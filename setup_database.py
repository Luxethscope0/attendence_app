# setup_database.py (V4-PostgreSQL)
import psycopg2
import psycopg2.errors
import os
import random
from datetime import datetime, timedelta
import numpy as np

# --- Re-use the connection function from database.py ---
# This is a bit of code duplication, but keeps this script standalone
def get_db_connection():

    DB_HOST = os.environ.get("DB_HOST")
    DB_PORT = os.environ.get("DB_PORT", "5432") # Default to 5432 if not set
    DB_NAME = os.environ.get("DB_NAME")
    DB_USER = os.environ.get("DB_USER")
    DB_PASS = os.environ.get("DB_PASS")

    # Check if all variables are set
    if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS]):
        # This error will only show up in the Streamlit app if secrets are missing
        st.error("Database is not configured. Please set all DB_* environment variables/secrets.")
        st.stop()

    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to PostgreSQL database. Is it running? Details: {e}")
        exit()

def setup_database():
    # --- 1. Connect and clear old tables ---
    conn = get_db_connection()
    cursor = conn.cursor()
    print("Connected to PostgreSQL database 'attendance_app'.")

    # Drop tables in reverse order of dependency
    print("Dropping existing tables...")
    tables_to_drop = [
        "qr_scans", "attendance_sessions",
        "student_grades", "grade_items", "grade_types",
        "attendance", "leave_requests", "enrollment_requests", "class_schedule",
        "section_enrollments", "sections", "subjects", "students",
        "registration_requests", "branches", "programs", "levels_of_study",
        "users", "semesters", "days_of_week", "time_slots"
    ]
    for table in tables_to_drop:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            print(f"Dropped table {table}.")
        except psycopg2.Error as e:
            print(f"Could not drop table {table}: {e}")
            conn.rollback()

    conn.commit()
    print("Finished dropping tables.")

    # --- 2. Create the Final Schema (V4) ---
    print("Creating new V4 (hierarchical) schema for PostgreSQL...")

    # --- CORE TABLES ---
    # SERIAL is the PostgreSQL equivalent of AUTOINCREMENT
    cursor.execute('''
    CREATE TABLE semesters (
        id SERIAL PRIMARY KEY,
        semester_name TEXT UNIQUE NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        is_active BOOLEAN DEFAULT FALSE
    );
    ''')

    cursor.execute('''
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'teacher', 'student')),
        email TEXT UNIQUE
    );
    ''')

    # --- ACADEMIC STRUCTURE (V4) ---
    cursor.execute('''
    CREATE TABLE levels_of_study (
        id SERIAL PRIMARY KEY,
        level_name TEXT UNIQUE NOT NULL
    );
    ''')

    cursor.execute('''
    CREATE TABLE programs (
        id SERIAL PRIMARY KEY,
        program_name TEXT NOT NULL,
        program_code TEXT NOT NULL UNIQUE,
        level_id INTEGER,
        FOREIGN KEY (level_id) REFERENCES levels_of_study(id) ON DELETE CASCADE
    );
    ''')

    cursor.execute('''
    CREATE TABLE branches (
        id SERIAL PRIMARY KEY,
        branch_name TEXT NOT NULL,
        branch_code TEXT NOT NULL UNIQUE,
        program_id INTEGER,
        FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
    );
    ''')

    cursor.execute('''
    CREATE TABLE subjects (
        id SERIAL PRIMARY KEY,
        subject_name TEXT UNIQUE NOT NULL,
        branch_id INTEGER,
        semester_number INTEGER NOT NULL,
        FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE
    );
    ''')

    # --- STUDENT & REGISTRATION TABLES (V4) ---
    cursor.execute('''
    CREATE TABLE students (
        id SERIAL PRIMARY KEY,
        student_id_str TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        user_id INTEGER UNIQUE,
        branch_id INTEGER,
        program_id INTEGER,
        joining_year INTEGER NOT NULL,
        final_grade INTEGER,
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (program_id) REFERENCES programs(id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    ''')

    cursor.execute('''
    CREATE TABLE registration_requests (
        id SERIAL PRIMARY KEY,
        full_name TEXT NOT NULL,
        password TEXT NOT NULL,
        email TEXT UNIQUE,
        requested_level_id INTEGER,
        requested_program_id INTEGER,
        requested_branch_id INTEGER,
        status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Approved', 'Rejected')),
        FOREIGN KEY (requested_level_id) REFERENCES levels_of_study(id),
        FOREIGN KEY (requested_program_id) REFERENCES programs(id),
        FOREIGN KEY (requested_branch_id) REFERENCES branches(id)
    );
    ''')

    # --- SECTION & ENROLLMENT TABLES ---
    cursor.execute('''
    CREATE TABLE sections (
        id SERIAL PRIMARY KEY,
        section_name TEXT NOT NULL,
        subject_id INTEGER,
        teacher_id INTEGER,
        semester_id INTEGER,
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
        FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
    );
    ''')

    cursor.execute('''
    CREATE TABLE section_enrollments (
        section_id INTEGER,
        student_id INTEGER,
        semester_id INTEGER,
        PRIMARY KEY (section_id, student_id),
        FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
    );
    ''')

    # --- TIMETABLE TABLES ---
    cursor.execute('''
    CREATE TABLE days_of_week (
        id SERIAL PRIMARY KEY,
        day_name TEXT UNIQUE NOT NULL
    );
    ''')

    cursor.execute('''
    CREATE TABLE time_slots (
        id SERIAL PRIMARY KEY,
        slot_name TEXT NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        UNIQUE(slot_name, start_time, end_time)
    );
    ''')

    cursor.execute('''
    CREATE TABLE class_schedule (
        id SERIAL PRIMARY KEY,
        section_id INTEGER,
        day_id INTEGER,
        slot_id INTEGER,
        UNIQUE(section_id, day_id, slot_id),
        FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
        FOREIGN KEY (day_id) REFERENCES days_of_week(id),
        FOREIGN KEY (slot_id) REFERENCES time_slots(id)
    );
    ''')

    # --- ATTENDANCE & REQUESTS TABLES ---
    # Note: DATE type is used for dates
    cursor.execute('''
    CREATE TABLE attendance (
        id SERIAL PRIMARY KEY,
        student_id INTEGER,
        section_id INTEGER,
        semester_id INTEGER,
        date DATE NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Present', 'Absent', 'Excused')),
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
        FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
        UNIQUE(student_id, section_id, date)
    );
    ''')

    cursor.execute('''
    CREATE TABLE leave_requests (
        id SERIAL PRIMARY KEY,
        student_id INTEGER,
        semester_id INTEGER,
        date DATE NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Approved', 'Rejected')),
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
    );
    ''')

    cursor.execute('''
    CREATE TABLE enrollment_requests (
        id SERIAL PRIMARY KEY,
        student_id INTEGER,
        subject_id INTEGER,
        semester_id INTEGER,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Approved', 'Rejected')),
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
        FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
    );
    ''')

    cursor.execute('''
    CREATE TABLE grade_types (
        id SERIAL PRIMARY KEY,
        type_name TEXT UNIQUE NOT NULL
    );
    ''')

    cursor.execute('''
    CREATE TABLE grade_items (
        id SERIAL PRIMARY KEY,
        item_name TEXT NOT NULL,
        max_marks INTEGER NOT NULL,
        section_id INTEGER,
        grade_type_id INTEGER,
        FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE,
        FOREIGN KEY (grade_type_id) REFERENCES grade_types(id) ON DELETE SET NULL
    );
    ''')

    cursor.execute('''
    CREATE TABLE student_grades (
        id SERIAL PRIMARY KEY,
        student_id INTEGER,
        grade_item_id INTEGER,
        marks_obtained NUMERIC(5, 2), -- Allows for decimal marks like 10.5
        UNIQUE(student_id, grade_item_id),
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (grade_item_id) REFERENCES grade_items(id) ON DELETE CASCADE
    );
    ''')

    cursor.execute('''
    CREATE TABLE attendance_sessions (
        id SERIAL PRIMARY KEY,
        section_id INTEGER,
        session_uuid TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE
    );
    ''')

    cursor.execute('''
    CREATE TABLE qr_scans (
        id SERIAL PRIMARY KEY,
        session_id INTEGER,
        student_id INTEGER,
        scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(session_id, student_id), -- Prevents re-scanning
        FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    ''')

    conn.commit()
    print("Successfully created V4 schema for PostgreSQL.")

    # --- 3. Populate Static Data (V4) ---
    try:
        print("Populating V4 static data...")
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 4, 30)

        # Use RETURNING id to get the new ID
        cursor.execute(
            "INSERT INTO semesters (semester_name, start_date, end_date, is_active) VALUES (%s, %s, %s, %s) RETURNING id",
            ('Spring 2025', start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), True)
        )
        active_semester_id = cursor.fetchone()[0]
        print("Created and activated 'Spring 2025'.")

        sample_users = [
        ('admin', 'admin123', 'admin', 'admin@example.com'),
        ('prof_giri', 'pass123', 'teacher', 'giri@example.com'),
        ('prof_kumar', 'pass456', 'teacher', 'kumar@example.com')
        ]
        cursor.executemany("INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s)", sample_users)

        cursor.execute("INSERT INTO levels_of_study (level_name) VALUES (%s) RETURNING id", ('Undergraduate',))
        ug_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO levels_of_study (level_name) VALUES (%s) RETURNING id", ('Postgraduate',))
        pg_id = cursor.fetchone()[0]

        cursor.execute("INSERT INTO programs (program_name, program_code, level_id) VALUES (%s, %s, %s) RETURNING id", ('B.Tech', 'd', ug_id))
        btech_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO programs (program_name, program_code, level_id) VALUES (%s, %s, %s) RETURNING id", ('Integrated M.Tech', 'i', ug_id))
        integ_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO programs (program_name, program_code, level_id) VALUES (%s, %s, %s) RETURNING id", ('M.Tech', 'm', pg_id))
        mtech_id = cursor.fetchone()[0]

        cursor.execute("INSERT INTO branches (branch_name, branch_code, program_id) VALUES (%s, %s, %s) RETURNING id", ('Computer Science', 'cs', btech_id))
        cs_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO branches (branch_name, branch_code, program_id) VALUES (%s, %s, %s) RETURNING id", ('Electronics', 'ece', btech_id))
        ece_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO branches (branch_name, branch_code, program_id) VALUES (%s, %s, %s) RETURNING id", ('AI & DS', 'ai', integ_id))
        ai_id = cursor.fetchone()[0]
        print("Populated Levels, Programs, and Branches.")

        sample_subjects = [
            ('Maths I', cs_id, 1),
            ('Physics I', cs_id, 1),
            ('Data Structures', cs_id, 2),
            ('Basic Electronics', ece_id, 1),
            ('Intro to AI', ai_id, 1)
        ]
        cursor.executemany("INSERT INTO subjects (subject_name, branch_id, semester_number) VALUES (%s, %s, %s)", sample_subjects)
        conn.commit()
        print("Populated subjects.")

        days = [('Monday',), ('Tuesday',), ('Wednesday',), ('Thursday',), ('Friday',), ('Saturday',), ('Sunday',)]
        cursor.executemany("INSERT INTO days_of_week (day_name) VALUES (%s)", days)
        slots = [('Slot 1', '09:00', '09:50'), ('Slot 2', '10:00', '10:50'), ('Slot 3', '11:00', '11:50')]
        cursor.executemany("INSERT INTO time_slots (slot_name, start_time, end_time) VALUES (%s, %s, %s)", slots)
        conn.commit()
        print("Populated days and time slots.")

        cursor.execute("SELECT id FROM users WHERE username = 'prof_giri'")
        giri_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM subjects WHERE subject_name = 'Maths I'")
        math_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM subjects WHERE subject_name = 'Data Structures'")
        ds_id = cursor.fetchone()[0]

        # --- NEW: Populate default grade types ---
        print("Populating default grade types...")
        grade_types = [('Assignment',), ('Quiz',), ('Midterm Exam',), ('Final Exam',), ('Project',)]
        cursor.executemany("INSERT INTO grade_types (type_name) VALUES (%s)", grade_types)
        conn.commit()

        print("Populating demo students...")
        students_data = {}
        current_year_short = int(start_date.strftime('%y')) # 25

        demo_cs_names = ["Alex Johnson", "Beth Smith", "Charlie Brown"]
        for i, name in enumerate(demo_cs_names):
            student_id_str = f"cs{current_year_short}d{1001+i}"
            base_prob = np.random.uniform(0.70, 0.99)
            student_email = f"{student_id_str}@example.com"
            cursor.execute("INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s) RETURNING id", (student_id_str, student_id_str, 'student', student_email))
            user_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO students (student_id_str, full_name, user_id, branch_id, program_id, joining_year) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (student_id_str, name, user_id, cs_id, btech_id, start_date.year)
            )
            student_db_id = cursor.fetchone()[0]
            students_data[student_db_id] = {'base_prob': base_prob}

        demo_ai_names = ["Dana White", "Evan Grant"]
        for i, name in enumerate(demo_ai_names):
            student_id_str = f"ai{current_year_short}i{1001+i}"
            base_prob = np.random.uniform(0.70, 0.99)
            student_email = f"{student_id_str}@example.com"
            cursor.execute("INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s) RETURNING id", (student_id_str, student_id_str, 'student', student_email))
            user_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO students (student_id_str, full_name, user_id, branch_id, program_id, joining_year) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (student_id_str, name, user_id, ai_id, integ_id, start_date.year)
            )
            student_db_id = cursor.fetchone()[0]
            students_data[student_db_id] = {'base_prob': base_prob}

        conn.commit()
        print(f"Populated {len(students_data)} demo students.")

        cursor.execute("INSERT INTO sections (section_name, subject_id, teacher_id, semester_id) VALUES (%s, %s, %s, %s) RETURNING id", ('CS-Maths-S1', math_id, giri_id, active_semester_id))
        math_s1_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO sections (section_name, subject_id, teacher_id, semester_id) VALUES (%s, %s, %s, %s) RETURNING id", ('CS-DS-S1', ds_id, giri_id, active_semester_id))
        ds_s1_id = cursor.fetchone()[0]
        conn.commit()
        print("Populated demo sections.")

        cursor.execute("SELECT id FROM students WHERE branch_id = %s", (cs_id,))
        cs_students = cursor.fetchall()
        s1_enrollments = [(math_s1_id, s[0], active_semester_id) for s in cs_students]
        s2_enrollments = [(ds_s1_id, s[0], active_semester_id) for s in cs_students]

        args_str_s1 = b",".join(cursor.mogrify("(%s,%s,%s)", x) for x in s1_enrollments)
        cursor.execute(b"INSERT INTO section_enrollments (section_id, student_id, semester_id) VALUES " + args_str_s1)
        args_str_s2 = b",".join(cursor.mogrify("(%s,%s,%s)", x) for x in s2_enrollments)
        cursor.execute(b"INSERT INTO section_enrollments (section_id, student_id, semester_id) VALUES " + args_str_s2)

        conn.commit()
        print("Enrolled demo students.")

        print("Generating demo attendance data...")
        cursor.execute("SELECT section_id, student_id FROM section_enrollments WHERE semester_id = %s", (active_semester_id,))
        enrollments = cursor.fetchall()

        attendance_records = []
        current_date = start_date

        while current_date <= end_date:
            if current_date.weekday() < 5: # Mon-Fri
                date_str = current_date.strftime('%Y-%m-%d')
                for section_id, student_id in enrollments:
                    student_profile = students_data.get(student_id)
                    if not student_profile: continue
                    prob = student_profile['base_prob']
                    if current_date.weekday() == 4: prob *= 0.95
                    status = np.random.choice(['Present', 'Absent'], p=[prob, 1 - prob])
                    attendance_records.append((student_id, section_id, active_semester_id, date_str, status))
            current_date += timedelta(days=1)

        args_str_att = b",".join(cursor.mogrify("(%s,%s,%s,%s,%s)", x) for x in attendance_records)
        cursor.execute(b"INSERT INTO attendance (student_id, section_id, semester_id, date, status) VALUES " + args_str_att)

        conn.commit()
        print(f"Generated {len(attendance_records)} demo attendance records.")

    except Exception as e:
        print(f"An error occurred during data population: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
        print(f"Database 'attendance_app' created and populated successfully!")

if __name__ == "__main__":
    setup_database()