# database.py (V4-PostgreSQL)
import psycopg2
import psycopg2.errors
import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
from datetime import datetime, timedelta
import uuid
import os

# --- 1. CORE HELPER FUNCTIONS ---

def get_db_connection():
    """
    Connects to the PostgreSQL database.
    Remember to replace with your own credentials.
    """
    # Read the 5 credentials from environment variables
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
        st.error(f"Error: Could not connect to PostgreSQL database. Is it running? Details: {e}")
        st.stop()

def fetch_users_from_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    SELECT
        u.id,
        u.username,
        u.password,
        u.role,
        u.email,
        s.full_name
    FROM users u
    LEFT JOIN students s ON u.id = s.user_id
    """
    cursor.execute(query)
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    credentials = {'usernames': {}}
    roles = {}
    user_ids = {}

    for user_id, db_username, password, role, email, full_name in users:
        username_key = db_username.lower()
        display_name = full_name if full_name else db_username.capitalize()
        # We don't need to store the email in credentials,
        # but you *could* add it to a new dict if you wanted to display it.
        credentials['usernames'][username_key] = {'name': display_name, 'password': password, 'email': email} # <-- Added email
        roles[username_key] = role
        user_ids[username_key] = user_id

    return credentials, roles, user_ids

# --- 2. SEMESTER FUNCTIONS ---

def get_active_semester():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, semester_name FROM semesters WHERE is_active = TRUE")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result:
        return result
    else:
        return None, None

def get_all_semesters():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, semester_name, start_date, end_date, is_active FROM semesters ORDER BY start_date DESC", conn)
    conn.close()
    return df

def get_semester_details(semester_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT semester_name, start_date, end_date FROM semesters WHERE id = %s", (semester_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result:
        return result
    return None, None, None

def check_semester_overlap(start_date, end_date, existing_semester_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT 1 FROM semesters WHERE start_date <= %s AND end_date >= %s"
    params = [end_date.strftime('%Y-%m-%d'), start_date.strftime('%Y-%m-%d')]
    if existing_semester_id:
        query += " AND id != %s"
        params.append(existing_semester_id)
    query += " LIMIT 1"
    cursor.execute(query, tuple(params))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return True if result else False

def add_new_semester(name, start_date, end_date):
    if not name or not start_date or not end_date:
        st.error("Please fill out all fields."); return False
    if end_date <= start_date:
        st.error("Error: End date must be after the start date."); return False
    if check_semester_overlap(start_date, end_date):
        st.error("Error: Date range overlaps with an existing semester."); return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO semesters (semester_name, start_date, end_date, is_active) VALUES (%s, %s, %s, %s)",
            (name, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), False)
        )
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Semester '{name}' added!"); return True
    except psycopg2.errors.UniqueViolation:
        st.error(f"Error: Semester '{name}' already exists."); return False

def update_semester(semester_id, name, start_date, end_date):
    if not all([semester_id, name, start_date, end_date]):
        st.error("Please fill out all fields."); return False
    if end_date <= start_date:
        st.error("Error: End date must be after the start date."); return False
    if check_semester_overlap(start_date, end_date, existing_semester_id=semester_id):
        st.error("Error: Date range overlaps with another existing semester."); return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE semesters SET semester_name = %s, start_date = %s, end_date = %s WHERE id = %s",
            (name, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), semester_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Semester '{name}' updated!"); return True
    except psycopg2.errors.UniqueViolation:
        st.error(f"Error: Semester name '{name}' already exists."); return False

def delete_semester(semester_id):
    if not semester_id: return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM semesters WHERE id = %s", (semester_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Semester deleted!")
        return True
    except Exception as e:
        conn.rollback()
        if "foreign key" in str(e).lower():
             st.error("Error: This semester is 'Active' or has sections. Cannot delete.")
        else:
            st.error(f"An error occurred: {e}")
        cursor.close()
        conn.close()
        return False

def set_active_semester(semester_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE semesters SET is_active = FALSE")
        cursor.execute("UPDATE semesters SET is_active = TRUE WHERE id = %s", (semester_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Semester activated!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

# --- 3. ACADEMIC STRUCTURE (V4) ---

# --- L1: Levels of Study ---
def get_all_levels():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, level_name FROM levels_of_study ORDER BY level_name", conn)
    conn.close()
    return df

def add_level(name):
    if not name: st.error("Level name cannot be empty."); return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO levels_of_study (level_name) VALUES (%s)", (name,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Level '{name}' added."); return True
    except psycopg2.errors.UniqueViolation:
        st.error("This level already exists."); return False

def delete_level(level_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM levels_of_study WHERE id = %s", (level_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Level deleted."); return True
    except psycopg2.IntegrityError:
        conn.rollback()
        st.error("Cannot delete: This level is in use by programs."); return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


# --- L2: Programs ---
def get_all_programs():
    conn = get_db_connection()
    query = """
    SELECT p.id, p.program_name, p.program_code, l.level_name
    FROM programs p
    JOIN levels_of_study l ON p.level_id = l.id
    ORDER BY l.level_name, p.program_name
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_program(name, code, level_id):
    if not name or not code or not level_id: st.error("Please fill all fields."); return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO programs (program_name, program_code, level_id) VALUES (%s, %s, %s)", (name, code, level_id))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Program '{name}' added."); return True
    except psycopg2.errors.UniqueViolation:
        st.error("This program name or code already exists."); return False

def delete_program(program_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM programs WHERE id = %s", (program_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Program deleted."); return True
    except psycopg2.IntegrityError:
        conn.rollback()
        st.error("Cannot delete: This program is in use by branches or students."); return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

# --- L3: Branches ---
def get_all_branches():
    conn = get_db_connection()
    query = """
    SELECT b.id, b.branch_name, b.branch_code, p.program_name
    FROM branches b
    JOIN programs p ON b.program_id = p.id
    ORDER BY p.program_name, b.branch_name
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_branch(name, code, program_id):
    if not name or not code or not program_id: st.error("Please fill all fields."); return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO branches (branch_name, branch_code, program_id) VALUES (%s, %s, %s)", (name, code, program_id))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Branch '{name}' added."); return True
    except psycopg2.errors.UniqueViolation:
        st.error("This branch name or code already exists."); return False

def delete_branch(branch_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM branches WHERE id = %s", (branch_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Branch deleted."); return True
    except psycopg2.IntegrityError:
        conn.rollback()
        st.error("Cannot delete: This branch is in use by subjects or students."); return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

# --- L4/L5: Subjects ---
def get_all_subjects():
    conn = get_db_connection()
    query = """
    SELECT s.id, s.subject_name, s.semester_number, b.branch_name
    FROM subjects s
    JOIN branches b ON s.branch_id = b.id
    ORDER BY b.branch_name, s.semester_number, s.subject_name
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_subject(name, branch_id, semester_num):
    if not name or not branch_id or not semester_num: st.error("Please fill all fields."); return False
    if not (1 <= semester_num <= 10): st.error("Semester must be between 1 and 10."); return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO subjects (subject_name, branch_id, semester_number) VALUES (%s, %s, %s)", (name, branch_id, semester_num))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Subject '{name}' added."); return True
    except psycopg2.errors.UniqueViolation:
        st.error("This subject already exists."); return False

def delete_subject(subject_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Subject deleted."); return True
    except psycopg2.IntegrityError:
        conn.rollback()
        st.error("Cannot delete: This subject is in use by sections."); return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

# --- L6: Grade Types (Admin Managed) ---

def get_all_grade_types():
    """Fetches all grade types for the admin panel."""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, type_name FROM grade_types ORDER BY type_name", conn)
    conn.close()
    return df

def add_grade_type(name):
    """Adds a new grade type (e.g., 'Quiz', 'Midterm')."""
    if not name:
        st.error("Grade type name cannot be empty.")
        return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO grade_types (type_name) VALUES (%s)", (name,))
        conn.commit()
        st.success(f"Grade Type '{name}' added.")
        return True
    except psycopg2.errors.UniqueViolation:
        st.error(f"Error: Grade Type '{name}' already exists.")
        return False
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def delete_grade_type(type_id):
    """Deletes a grade type."""
    if not type_id:
        return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM grade_types WHERE id = %s", (type_id,))
        conn.commit()
        st.success("Grade Type deleted.")
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        st.error("Cannot delete: This grade type is in use by a grade item.")
        return False
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# --- 4. SIGNUP & REGISTRATION (V4) ---

def get_public_academic_structure():
    conn = get_db_connection()
    levels = pd.read_sql_query("SELECT id, level_name FROM levels_of_study", conn)
    programs = pd.read_sql_query("SELECT id, program_name, level_id FROM programs", conn)
    branches = pd.read_sql_query("SELECT id, branch_name, program_id FROM branches", conn)
    conn.close()
    return levels, programs, branches

def submit_registration_request(full_name, email, password, level_id, program_id, branch_id):
    if not all([full_name, email, password, level_id, program_id, branch_id]):
        st.error("Please fill out all fields.")
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed_password = stauth.Hasher().hash(password)
        cursor.execute(
        """
        INSERT INTO registration_requests
        (full_name, email, password, requested_level_id, requested_program_id, requested_branch_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (full_name, email, hashed_password, level_id, program_id, branch_id, 'Pending')
        )
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Registration successful! Pending admin approval."); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_pending_registrations():
    conn = get_db_connection()
    query = """
    SELECT
        r.id, r.full_name,
        l.level_name, p.program_name, b.branch_name
    FROM registration_requests r
    JOIN levels_of_study l ON r.requested_level_id = l.id
    JOIN programs p ON r.requested_program_id = p.id
    JOIN branches b ON r.requested_branch_id = b.id
    WHERE r.status = 'Pending'
    ORDER BY r.id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_next_student_id(branch_id, program_id, joining_year):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT branch_code FROM branches WHERE id = %s", (branch_id,))
    branch_code = cursor.fetchone()[0]
    cursor.execute("SELECT program_code FROM programs WHERE id = %s", (program_id,))
    program_code = cursor.fetchone()[0]
    year_short = str(joining_year)[-2:]

    prefix = f"{branch_code}{year_short}{program_code}"

    query = "SELECT student_id_str FROM students WHERE student_id_str LIKE %s ORDER BY student_id_str DESC LIMIT 1"
    cursor.execute(query, (f"{prefix}%",))
    last_id = cursor.fetchone()
    cursor.close()
    conn.close()

    if last_id is None:
        next_id_num = 1001
    else:
        try:
            last_id_num = int(last_id[0][len(prefix):])
            next_id_num = last_id_num + 1
        except (ValueError, IndexError):
            next_id_num = 1001

    return f"{prefix}{next_id_num}"

def approve_registration(request_id, generated_student_id, joining_year):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
        "SELECT full_name, email, password, requested_program_id, requested_branch_id FROM registration_requests WHERE id = %s",
        (request_id,)
        )
        req = cursor.fetchone()

        if not req: st.error("Request not found."); return False

        full_name, email, password, program_id, branch_id = req

        # Create user
        # Note: RETURNING id is PostgreSQL-specific, replaces cursor.lastrowid
        cursor.execute(
        "INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s) RETURNING id",
        (generated_student_id, password, 'student', email)
        )
        new_user_id = cursor.fetchone()[0]

        # Create student
        cursor.execute(
            """
            INSERT INTO students (student_id_str, full_name, user_id, branch_id, program_id, joining_year)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (generated_student_id, full_name, new_user_id, branch_id, program_id, joining_year)
        )

        # Delete request
        cursor.execute("DELETE FROM registration_requests WHERE id = %s", (request_id,))
        conn.commit()
        st.success(f"Student '{full_name}' approved with ID '{generated_student_id}'!"); return True

    except psycopg2.errors.UniqueViolation as e:
        conn.rollback(); st.error(f"Failed: User ID '{generated_student_id}' may already exist. {e}"); return False
    except Exception as e:
        conn.rollback(); st.error(f"An error occurred: {e}"); return False
    finally:
        cursor.close()
        conn.close()

def reject_registration(request_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM registration_requests WHERE id = %s", (request_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Request rejected."); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); return False

def get_registration_request_details(request_id):
    """
    Fetches the program and branch ID for a specific registration request.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT requested_program_id, requested_branch_id FROM registration_requests WHERE id = %s", (request_id,))
    req_data = cursor.fetchone()
    cursor.close()
    conn.close()
    # Ensure we return a tuple even if not found, to avoid errors
    return req_data if req_data else (None, None)

# --- 5. ADMIN & TEACHER FUNCTIONS ---

def get_all_teachers():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, username FROM users WHERE role = 'teacher'", conn)
    conn.close()
    return df.set_index('id')['username'].to_dict()

def get_all_sections(semester_id):
    conn = get_db_connection()
    query = """
    SELECT s.id, s.section_name, sub.subject_name, u.username AS teacher_name
    FROM sections s
    JOIN subjects sub ON s.subject_id = sub.id
    JOIN users u ON s.teacher_id = u.id
    WHERE s.semester_id = %s
    ORDER BY sub.subject_name, s.section_name
    """
    df = pd.read_sql_query(query, conn, params=(semester_id,))
    conn.close()
    df['display_name'] = df['section_name'] + " (" + df['subject_name'] + ", " + df['teacher_name'] + ")"
    return df.set_index('id')['display_name'].to_dict()

def get_all_students_for_admin():
    conn = get_db_connection()
    query = """
    SELECT s.id, s.student_id_str, b.branch_name
    FROM students s
    JOIN branches b ON s.branch_id = b.id
    ORDER BY b.branch_name, s.student_id_str
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['display_name'] = df['student_id_str'] + " (" + df['branch_name'] + ")"
    return df.set_index('id')['display_name'].to_dict()

def get_student_details(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT student_id_str, branch_id, program_id, joining_year, final_grade FROM students WHERE id = %s",
        (student_id,)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

def add_new_teacher(username, password):
    if not username or not password: st.error("Please fill out all fields."); return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        hashed_password = stauth.Hasher().hash(password)
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", (username, hashed_password, 'teacher'))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Teacher '{username}' added!"); return True
    except psycopg2.errors.UniqueViolation:
        st.error(f"Error: Username '{username}' already exists."); return False

def delete_teacher(teacher_id):
    if not teacher_id: return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s AND role = 'teacher'", (teacher_id,))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Teacher deleted!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def add_new_section(section_name, subject_id, teacher_id, semester_id):
    if not all([section_name, subject_id, teacher_id, semester_id]): st.error("Please fill out all fields."); return False
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT branch_id FROM subjects WHERE id = %s", (subject_id,))
        branch_id_result = cursor.fetchone()
        if not branch_id_result: st.error("Error: This subject is not linked to any branch."); return False
        branch_id = branch_id_result[0]

        cursor.execute("SELECT id FROM students WHERE branch_id = %s", (branch_id,))
        all_branch_students = cursor.fetchall()
        all_branch_student_ids = {s[0] for s in all_branch_students}

        cursor.execute(
            """
            SELECT se.student_id FROM section_enrollments se
            JOIN sections s ON se.section_id = s.id
            WHERE s.subject_id = %s AND se.semester_id = %s
            """,
            (subject_id, semester_id)
        )
        enrolled_students = cursor.fetchall()
        enrolled_student_ids = {s[0] for s in enrolled_students}

        available_student_ids = list(all_branch_student_ids - enrolled_student_ids)

        cursor.execute(
            "INSERT INTO sections (section_name, subject_id, teacher_id, semester_id) VALUES (%s, %s, %s, %s) RETURNING id",
            (section_name, subject_id, teacher_id, semester_id)
        )
        new_section_id = cursor.fetchone()[0]

        if available_student_ids:
            new_enrollments = [(new_section_id, s_id, semester_id) for s_id in available_student_ids]
            # psycopg2 requires executemany to be formatted differently
            args_str = b",".join(cursor.mogrify("(%s,%s,%s)", x) for x in new_enrollments)
            cursor.execute(b"INSERT INTO section_enrollments (section_id, student_id, semester_id) VALUES " + args_str)

        conn.commit()
        st.success(f"Section '{section_name}' created! Auto-enrolled {len(available_student_ids)} students from the branch."); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); return False
    finally:
        cursor.close()
        conn.close()

def delete_section(section_id):
    if not section_id: return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sections WHERE id = %s", (section_id,));
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Section deleted!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_enrollment_data(section_id, semester_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT s.branch_id, sec.subject_id
        FROM subjects s
        JOIN sections sec ON s.id = sec.subject_id
        WHERE sec.id = %s
        """,
        (section_id,)
    )
    section_info = cursor.fetchone()

    if not section_info:
        conn.close()
        st.error(f"Error: Could not find branch/subject for section {section_id}.")
        return pd.DataFrame(columns=['id', 'display_name']), pd.DataFrame(columns=['id', 'display_name'])

    branch_id, subject_id = section_info

    enrolled_query = """
    SELECT s.id, s.student_id_str, b.branch_name
    FROM students s
    JOIN section_enrollments se ON s.id = se.student_id
    JOIN branches b ON s.branch_id = b.id
    WHERE se.section_id = %s AND se.semester_id = %s
    ORDER BY b.branch_name, s.student_id_str
    """
    enrolled_df = pd.read_sql_query(enrolled_query, conn, params=(section_id, semester_id))
    if not enrolled_df.empty:
        enrolled_df['display_name'] = enrolled_df['student_id_str'] + " (" + enrolled_df['branch_name'] + ")"

    available_query = """
    SELECT s.id, s.student_id_str, b.branch_name
    FROM students s
    JOIN branches b ON s.branch_id = b.id
    WHERE s.branch_id = %s
    AND s.id NOT IN (
        SELECT se_inner.student_id
        FROM section_enrollments se_inner
        JOIN sections s_inner ON se_inner.section_id = s_inner.id
        WHERE s_inner.subject_id = %s AND se_inner.semester_id = %s
    )
    ORDER BY b.branch_name, s.student_id_str
    """
    available_df = pd.read_sql_query(available_query, conn, params=(branch_id, subject_id, semester_id))
    if not available_df.empty:
        available_df['display_name'] = available_df['student_id_str'] + " (" + available_df['branch_name'] + ")"

    conn.close()
    return enrolled_df, available_df


def update_enrollments(section_id, new_enrolled_student_ids, semester_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM section_enrollments WHERE section_id = %s", (section_id,))
        if new_enrolled_student_ids:
            new_enrollments = [(section_id, s_id, semester_id) for s_id in new_enrolled_student_ids]
            args_str = b",".join(cursor.mogrify("(%s,%s,%s)", x) for x in new_enrollments)
            cursor.execute(b"INSERT INTO section_enrollments (section_id, student_id, semester_id) VALUES " + args_str)
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Enrollments updated successfully!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def update_student_data(student_id, new_student_id_str, new_full_name, new_branch_id, new_program_id, new_joining_year, new_final_grade):
    if not all([student_id, new_student_id_str, new_full_name, new_branch_id, new_program_id, new_joining_year]):
        st.error("Please fill out all required fields."); return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM students WHERE id = %s", (student_id,))
        user_id = cursor.fetchone()[0]

        cursor.execute(
            """
            UPDATE students
            SET student_id_str = %s, full_name = %s, branch_id = %s, program_id = %s, joining_year = %s, final_grade = %s
            WHERE id = %s
            """,
            (new_student_id_str, new_full_name, new_branch_id, new_program_id, new_joining_year, new_final_grade, student_id)
        )

        if user_id:
            cursor.execute("UPDATE users SET username = %s WHERE id = %s", (new_student_id_str, user_id))

        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Student '{new_student_id_str}' updated!"); return True
    except psycopg2.errors.UniqueViolation:
        st.error(f"Error: Student ID '{new_student_id_str}' already exists."); conn.rollback(); cursor.close(); conn.close(); return False
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def delete_student(student_id):
    if not student_id: return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM students WHERE id = %s", (student_id,))
        user_id_result = cursor.fetchone()

        cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
        if user_id_result:
            user_id = user_id_result[0]
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))

        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Student deleted!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_pending_leave_requests(semester_id):
    conn = get_db_connection()
    query = "SELECT lr.id, s.student_id_str, lr.date, lr.reason FROM leave_requests lr JOIN students s ON lr.student_id = s.id WHERE lr.semester_id = %s AND lr.status = 'Pending' ORDER BY lr.date"
    df = pd.read_sql_query(query, conn, params=(semester_id,)); conn.close()
    return df

def update_leave_request(request_id, new_status):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE leave_requests SET status = %s WHERE id = %s", (new_status, request_id))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Request {new_status.lower()}!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_leave_request_history(semester_id):
    conn = get_db_connection()
    query = "SELECT s.student_id_str, lr.date, lr.reason, lr.status FROM leave_requests lr JOIN students s ON lr.student_id = s.id WHERE lr.semester_id = %s AND lr.status != 'Pending' ORDER BY lr.date DESC"
    df = pd.read_sql_query(query, conn, params=(semester_id,)); conn.close()
    return df

def get_pending_enrollment_requests(semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        er.id, s.student_id_str, b.branch_name AS student_branch,
        sub.subject_name AS requested_subject, er.reason
    FROM enrollment_requests er
    JOIN students s ON er.student_id = s.id
    JOIN branches b ON s.branch_id = b.id
    JOIN subjects sub ON er.subject_id = sub.id
    WHERE er.semester_id = %s AND er.status = 'Pending'
    ORDER BY er.id
    """
    df = pd.read_sql_query(query, conn, params=(semester_id,)); conn.close()
    return df

def get_request_details_for_approval(request_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT student_id, subject_id FROM enrollment_requests WHERE id = %s", (request_id,)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result if result else (None, None)

def get_sections_for_subject(subject_id, semester_id):
    conn = get_db_connection()
    query = """
    SELECT s.id, s.section_name, u.username AS teacher_name
    FROM sections s
    JOIN users u ON s.teacher_id = u.id
    WHERE s.subject_id = %s AND s.semester_id = %s
    ORDER BY s.section_name
    """
    df = pd.read_sql_query(query, conn, params=(subject_id, semester_id))
    conn.close()
    df['display_name'] = df['section_name'] + " (" + df['teacher_name'] + ")"
    return df.set_index('id')['display_name'].to_dict()

def update_enrollment_request_status(request_id, new_status):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE enrollment_requests SET status = %s WHERE id = %s", (new_status, request_id))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error updating request status: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_enrollment_request_history(semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        s.student_id_str, sub.subject_name AS requested_subject,
        er.reason, er.status
    FROM enrollment_requests er
    JOIN students s ON er.student_id = s.id
    JOIN subjects sub ON er.subject_id = sub.id
    WHERE er.semester_id = %s AND er.status != 'Pending'
    ORDER BY er.id DESC
    """
    df = pd.read_sql_query(query, conn, params=(semester_id,)); conn.close()
    return df

def get_admin_dashboard_data(semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        a.status,
        b.branch_name,
        sub.subject_name,
        sec.section_name,
        u.username AS teacher_name
    FROM attendance a
    JOIN students s ON a.student_id = s.id
    JOIN branches b ON s.branch_id = b.id
    JOIN sections sec ON a.section_id = sec.id
    JOIN subjects sub ON sec.subject_id = sub.id
    JOIN users u ON sec.teacher_id = u.id
    WHERE a.semester_id = %s
    """
    df = pd.read_sql_query(query, conn, params=(semester_id,))
    conn.close()
    return df

def get_pending_counts(semester_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(id) FROM leave_requests WHERE semester_id = %s AND status = 'Pending'", (semester_id,))
    pending_leave = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(id) FROM enrollment_requests WHERE semester_id = %s AND status = 'Pending'", (semester_id,))
    pending_enroll = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(id) FROM registration_requests WHERE status = 'Pending'")
    pending_regs = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return pending_leave, pending_enroll, pending_regs

# --- Add this to the end of database.py, maybe with other Admin functions ---

# --- In database.py ---
# --- REPLACE the old get_low_attendance_students with this one ---

def get_low_attendance_students(semester_id, threshold=75.0):
    """
    Finds all students (and their emails) whose attendance percentage
    in any subject is below the given threshold.
    """
    conn = get_db_connection()
    query = """
    WITH AttendanceStats AS (
        SELECT
            a.student_id,
            sec.subject_id,
            SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) AS present_count,
            COUNT(a.id) AS total_graded_classes
        FROM
            attendance a
        JOIN
            sections sec ON a.section_id = sec.id
        WHERE
            a.semester_id = %s
            AND a.status IN ('Present', 'Absent')
        GROUP BY
            a.student_id, sec.subject_id
    )
    SELECT
        s.student_id_str,
        s.full_name,
        u.email, -- <-- THE NEWLY ADDED COLUMN
        sub.subject_name,
        (stat.present_count::FLOAT / stat.total_graded_classes::FLOAT) * 100 AS attendance_percentage
    FROM
        AttendanceStats stat
    JOIN
        students s ON stat.student_id = s.id
    JOIN
        users u ON s.user_id = u.id -- <-- THE NEW JOIN
    JOIN
        subjects sub ON stat.subject_id = sub.id
    WHERE
        (stat.present_count::FLOAT / stat.total_graded_classes::FLOAT) * 100 < %s
    ORDER BY
        s.full_name, sub.subject_name;
    """
    df = pd.read_sql_query(query, conn, params=(semester_id, threshold))
    conn.close()
    return df

# --- 6. TEACHER-SPECIFIC FUNCTIONS ---

def get_teacher_sections(teacher_id, semester_id):
    conn = get_db_connection()
    query = "SELECT s.id, s.section_name, sub.subject_name FROM sections s JOIN subjects sub ON s.subject_id = sub.id WHERE s.teacher_id = %s AND s.semester_id = %s ORDER BY sub.subject_name, s.section_name"
    df = pd.read_sql_query(query, conn, params=(teacher_id, semester_id)); conn.close()
    df['display_name'] = df['section_name'] + " (" + df['subject_name'] + ")"
    return df.set_index('id')['display_name'].to_dict()

def get_teacher_subjects_list(teacher_id, semester_id):
    conn = get_db_connection()
    query = "SELECT DISTINCT sub.id, sub.subject_name FROM subjects sub JOIN sections sec ON sub.id = sec.subject_id WHERE sec.teacher_id = %s AND sec.semester_id = %s ORDER BY sub.subject_name"
    df = pd.read_sql_query(query, conn, params=(teacher_id, semester_id)); conn.close()
    return df.set_index('id')['subject_name'].to_dict()

def get_teacher_branches_list(teacher_id, semester_id):
    conn = get_db_connection()
    query = """
    SELECT DISTINCT b.id, b.branch_name FROM branches b
    JOIN students s ON b.id = s.branch_id
    JOIN section_enrollments se ON s.id = se.student_id
    JOIN sections sec ON se.section_id = sec.id
    WHERE sec.teacher_id = %s AND sec.semester_id = %s
    ORDER BY b.branch_name
    """
    df = pd.read_sql_query(query, conn, params=(teacher_id, semester_id)); conn.close()
    return df.set_index('id')['branch_name'].to_dict()

def fetch_teacher_dashboard_data(teacher_id, semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        s.id AS section_id, s.section_name, sub.subject_name, a.date, a.status,
        st.student_id_str, st.final_grade, b.branch_name AS batch
    FROM attendance a
    JOIN sections s ON a.section_id = s.id
    JOIN subjects sub ON s.subject_id = sub.id
    JOIN students st ON a.student_id = st.id
    JOIN branches b ON st.branch_id = b.id
    WHERE s.teacher_id = %s AND s.semester_id = %s
    """
    df = pd.read_sql_query(query, conn, params=(teacher_id, semester_id)); conn.close()
    all_sections_df = pd.DataFrame(get_teacher_sections(teacher_id, semester_id).items(), columns=['section_id', 'section_name_display'])
    if df.empty:
        df = all_sections_df.rename(columns={'section_name_display': 'Section'})
    else:
        df['Section'] = df['section_name'] + " (" + df['subject_name'] + ")"
        df = pd.merge(all_sections_df.rename(columns={'section_name_display': 'Section'}), df, on='Section', how='left')
    df = df.rename(columns={'student_id_str': 'StudentID', 'date': 'Date', 'status': 'AttendanceStatus', 'final_grade': 'FinalGrade', 'batch': 'Batch'})
    if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date'])
    return df

def get_roster_with_attendance(section_id, date_str):
    conn = get_db_connection()
    query = """
    WITH RankedLeaveRequests AS (
        SELECT student_id, date, status, ROW_NUMBER() OVER(PARTITION BY student_id, date ORDER BY CASE status WHEN 'Approved' THEN 1 WHEN 'Pending'  THEN 2 WHEN 'Rejected' THEN 3 END) as rn
        FROM leave_requests WHERE date = %s
    )
    SELECT
        s.id, s.student_id_str, b.branch_name AS batch,
        CASE
            WHEN lr.status = 'Approved' THEN 'Excused'
            WHEN lr.status = 'Pending' THEN 'Pending'
            WHEN lr.status = 'Rejected' THEN 'Rejected'
            ELSE COALESCE(a.status, 'Present')
        END AS Status
    FROM students s
    JOIN section_enrollments se ON s.id = se.student_id
    JOIN branches b ON s.branch_id = b.id
    LEFT JOIN attendance a ON s.id = a.student_id AND a.section_id = %s AND a.date = %s
    LEFT JOIN RankedLeaveRequests lr ON s.id = lr.student_id AND lr.rn = 1
    WHERE se.section_id = %s
    ORDER BY b.branch_name, s.student_id_str
    """
    params = (date_str, section_id, date_str, section_id)
    df = pd.read_sql_query(query, conn, params=params); conn.close()
    return df

def save_attendance(section_id, date, attendance_dict, semester_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    date_str = date.strftime('%Y-%m-%d')
    try:
        cursor.execute("DELETE FROM attendance WHERE section_id = %s AND date = %s", (section_id, date_str))
        new_records = [(student_id, section_id, semester_id, date_str, status) for student_id, status in attendance_dict.items() if status in ('Present', 'Absent')]
        if new_records:
            args_str = b",".join(cursor.mogrify("(%s,%s,%s,%s,%s)", x) for x in new_records)
            cursor.execute(b"INSERT INTO attendance (student_id, section_id, semester_id, date, status) VALUES " + args_str)
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Attendance saved successfully!"); return True
    except Exception as e:
        st.error(f"An error occurred while saving: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def smart_student_lookup(teacher_id, date_str, semester_id, section_id=None, subject_id=None, branch_id=None, student_id_str=None):
    conn = get_db_connection()
    query = """
    WITH RankedLeaveRequests AS (
        SELECT student_id, date, status, ROW_NUMBER() OVER(PARTITION BY student_id, date ORDER BY CASE status WHEN 'Approved' THEN 1 WHEN 'Pending'  THEN 2 WHEN 'Rejected' THEN 3 END) as rn
        FROM leave_requests WHERE date = %s
    )
    SELECT
        s.student_id_str, b.branch_name AS branch, sub.subject_name AS subject, sec.section_name,
        CASE
            WHEN lr.status = 'Approved' THEN 'Excused'
            WHEN lr.status = 'Pending' THEN 'Pending'
            WHEN lr.status = 'Rejected' THEN 'Rejected'
            ELSE COALESCE(a.status, 'N/A')
        END AS status
    FROM students s
    JOIN branches b ON s.branch_id = b.id
    JOIN section_enrollments se ON s.id = se.student_id
    JOIN sections sec ON se.section_id = sec.id
    JOIN subjects sub ON sec.subject_id = sub.id
    LEFT JOIN attendance a ON s.id = a.student_id AND a.section_id = sec.id AND a.date = %s
    LEFT JOIN RankedLeaveRequests lr ON s.id = lr.student_id AND lr.rn = 1
    WHERE sec.teacher_id = %s AND se.semester_id = %s
    """
    params = [date_str, date_str, teacher_id, semester_id]
    if section_id: query += " AND sec.id = %s"; params.append(section_id)
    if subject_id: query += " AND sec.subject_id = %s"; params.append(subject_id)
    if branch_id: query += " AND s.branch_id = %s"; params.append(branch_id)
    if student_id_str: query += " AND s.student_id_str = %s"; params.append(student_id_str)
    query += " ORDER BY s.student_id_str, sub.subject_name"
    df = pd.read_sql_query(query, conn, params=tuple(params)); conn.close()
    df_final = df[df['status'] != 'N/A'].drop_duplicates()
    return df_final

def get_attendance_summary(section_id):
    conn = get_db_connection()
    query = "SELECT DISTINCT date FROM attendance WHERE section_id = %s ORDER BY date"
    df = pd.read_sql_query(query, conn, params=(section_id,)); conn.close()
    if df.empty: return pd.DataFrame(columns=["Dates Taken"]), pd.DataFrame(columns=["Dates Missed"])
    dates_taken_df = pd.DataFrame(sorted(list(pd.to_datetime(df['date']).dt.date), reverse=True), columns=["Dates Taken"])
    if dates_taken_df.empty: return pd.DataFrame(columns=["Dates Taken"]), pd.DataFrame(columns=["Dates Missed"])
    min_date = dates_taken_df["Dates Taken"].min(); max_date = datetime.now().date()
    all_weekdays = pd.bdate_range(start=min_date, end=max_date).date
    set_taken = set(dates_taken_df["Dates Taken"])
    set_expected = set(all_weekdays)
    dates_missed_df = pd.DataFrame(sorted(list(set_expected - set_taken), reverse=True), columns=["Dates Missed"])
    return dates_taken_df, dates_missed_df

def check_date_status(section_id, date_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT EXISTS(SELECT 1 FROM attendance WHERE section_id = %s AND date = %s LIMIT 1)"
    cursor.execute(query, (section_id, date_str))
    result = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return result == 1

# --- 7. STUDENT-SPECIFIC FUNCTIONS ---

def get_student_profile(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM students WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result: return result[0]
    return None

def get_student_enrollments(student_id, semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        sub.subject_name, s.section_name, u.username AS teacher_name
    FROM section_enrollments se
    JOIN sections s ON se.section_id = s.id
    JOIN subjects sub ON s.subject_id = sub.id
    JOIN users u ON s.teacher_id = u.id
    WHERE se.student_id = %s AND se.semester_id = %s
    ORDER BY sub.subject_name, s.section_name
    """
    df = pd.read_sql_query(query, conn, params=(student_id, semester_id))
    conn.close()
    return df

def get_student_email(student_id):
    """Fetches a student's email via their user_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    SELECT u.email
    FROM users u
    JOIN students s ON u.id = s.user_id
    WHERE s.id = %s
    """
    cursor.execute(query, (student_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None

def get_student_branch_id(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT branch_id FROM students WHERE id = %s", (student_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None

def get_available_sections(student_id, branch_id, semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        s.id AS section_id, s.section_name,
        sub.subject_name, u.username AS teacher_name
    FROM sections s
    JOIN subjects sub ON s.subject_id = sub.id
    JOIN users u ON s.teacher_id = u.id
    WHERE s.semester_id = %s
    AND sub.branch_id = %s
    AND sub.id NOT IN (
        SELECT s_inner.subject_id
        FROM section_enrollments se_inner
        JOIN sections s_inner ON se_inner.section_id = s_inner.id
        WHERE se_inner.student_id = %s AND se_inner.semester_id = %s
    )
    ORDER BY sub.subject_name, s.section_name
    """
    df = pd.read_sql_query(query, conn, params=(semester_id, branch_id, student_id, semester_id))
    conn.close()
    return df

def enroll_student_in_section(student_id, section_id, semester_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO section_enrollments (section_id, student_id, semester_id) VALUES (%s, %s, %s)",
            (section_id, student_id, semester_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Enrollment successful!"); return True
    except psycopg2.errors.UniqueViolation:
        st.error("Error: You are already enrolled in this section or a section for this subject."); return False
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_off_branch_subjects(branch_id, semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        sub.id, sub.subject_name, b.branch_name
    FROM subjects sub
    JOIN branches b ON sub.branch_id = b.id
    WHERE sub.branch_id != %s
    AND sub.id IN (SELECT subject_id FROM sections WHERE semester_id = %s)
    ORDER BY b.branch_name, sub.subject_name
    """
    df = pd.read_sql_query(query, conn, params=(branch_id, semester_id))
    conn.close()
    df['display_name'] = df['subject_name'] + " (" + df['branch_name'] + ")"
    return df.set_index('id')['display_name'].to_dict()

def submit_enrollment_request(student_id, subject_id, semester_id, reason):
    if not all([student_id, subject_id, semester_id, reason]):
        st.error("Please select a subject and provide a reason."); return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM enrollment_requests WHERE student_id = %s AND subject_id = %s AND semester_id = %s AND status IN ('Pending', 'Approved')",
            (student_id, subject_id, semester_id)
        )
        exists = cursor.fetchone()
        if exists:
            st.error("You already have a Pending or Approved request for this subject."); return False

        cursor.execute(
            "INSERT INTO enrollment_requests (student_id, subject_id, semester_id, reason, status) VALUES (%s, %s, %s, %s, %s)",
            (student_id, subject_id, semester_id, reason, 'Pending')
        )
        conn.commit()
        cursor.close()
        conn.close()
        st.success("Enrollment request submitted!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_student_enrollment_requests(student_id, semester_id):
    conn = get_db_connection()
    query = """
    SELECT
        sub.subject_name, b.branch_name, er.reason, er.status
    FROM enrollment_requests er
    JOIN subjects sub ON er.subject_id = sub.id
    JOIN branches b ON sub.branch_id = b.id
    WHERE er.student_id = %s AND er.semester_id = %s
    ORDER BY er.id DESC
    """
    df = pd.read_sql_query(query, conn, params=(student_id, semester_id))
    conn.close()
    return df

def submit_leave_request(student_id, semester_id, date, reason):
    if not all([student_id, semester_id, date, reason]):
        st.error("Please fill out all fields."); return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        date_str = date.strftime('%Y-%m-%d')
        cursor.execute("SELECT 1 FROM leave_requests WHERE student_id = %s AND date = %s AND status IN ('Pending', 'Approved')", (student_id, date_str))
        exists = cursor.fetchone()
        if exists:
            st.error("You have already submitted a request for this date that is Pending or Approved."); return False
        cursor.execute("INSERT INTO leave_requests (student_id, semester_id, date, reason, status) VALUES (%s, %s, %s, %s, %s)", (student_id, semester_id, date_str, reason, 'Pending'))
        conn.commit()
        cursor.close()
        conn.close()
        st.success(f"Leave request for {date_str} submitted!"); return True
    except Exception as e:
        st.error(f"An error occurred: {e}"); conn.rollback(); cursor.close(); conn.close(); return False

def get_student_leave_requests(student_id, semester_id):
    conn = get_db_connection()
    query = "SELECT date, reason, status FROM leave_requests WHERE student_id = %s AND semester_id = %s ORDER BY date DESC, id DESC"
    df = pd.read_sql_query(query, conn, params=(student_id, semester_id))
    conn.close()
    return df

def fetch_student_dashboard_data(student_id, semester_id):
    conn = get_db_connection()
    # 1. Get enrollments
    enroll_query = """
    SELECT
        s.id AS section_id, s.section_name,
        sub.subject_name, u.username AS teacher_name
    FROM section_enrollments se
    JOIN sections s ON se.section_id = s.id
    JOIN subjects sub ON s.subject_id = sub.id
    JOIN users u ON s.teacher_id = u.id
    WHERE se.student_id = %s AND se.semester_id = %s
    """
    df_enroll = pd.read_sql_query(enroll_query, conn, params=(student_id, semester_id))
    if df_enroll.empty:
        conn.close()
        return pd.DataFrame(columns=['Section', 'section_id'])
    df_enroll['Section'] = df_enroll['section_name'] + " (" + df_enroll['teacher_name'] + ") (" + df_enroll['subject_name'] + ")"

    # 2. Get attendance
    att_query = "SELECT section_id, date, status FROM attendance a WHERE a.student_id = %s AND a.semester_id = %s"
    df_att = pd.read_sql_query(att_query, conn, params=(student_id, semester_id))

    # 3. Get leave
    leave_query = "SELECT date, status FROM leave_requests lr WHERE lr.student_id = %s AND lr.semester_id = %s AND lr.status != 'Pending'"
    df_leave = pd.read_sql_query(leave_query, conn, params=(student_id, semester_id))
    conn.close() # Close connection after all queries
    df_leave['status'] = df_leave['status'].replace('Approved', 'Excused')

    # 4. Merge attendance
    df_att_full = pd.merge(df_att, df_enroll, on='section_id', how='left')

    # 5. Expand leaves
    df_leave_expanded = pd.DataFrame()
    if not df_leave.empty and not df_enroll.empty:
         df_leave_expanded = df_enroll.assign(key=1).merge(df_leave.assign(key=1), on='key').drop('key', axis=1)

    # 6. Combine
    cols = ['Section', 'section_id', 'date', 'status']
    df_att_simple = df_att_full[cols]
    df_leave_simple = pd.DataFrame()
    if not df_leave_expanded.empty:
        df_leave_simple = df_leave_expanded[cols]

    df_combined = pd.concat([df_att_simple, df_leave_simple])
    if df_combined.empty:
        return df_enroll[['Section']]

    # 7. Prioritize
    df_combined['status_priority'] = df_combined['status'].map({'Excused': 1, 'Present': 2, 'Absent': 3, 'Rejected': 4})
    df_final = df_combined.sort_values(by='status_priority').drop_duplicates(subset=['Section', 'date'], keep='first')

    # 8. Merge with shell
    df_final = pd.merge(
        df_enroll[['Section']].drop_duplicates(),
        df_final,
        on='Section',
        how='left'
    )
    if 'Date' in df_final.columns:
        df_final['Date'] = pd.to_datetime(df_final['Date'])
    return df_final.rename(columns={'status': 'AttendanceStatus', 'date': 'Date'})

def get_student_grades_summary(student_id, semester_id):
    """Fetches all grade items and marks for a student in a given semester, grouped by subject."""
    conn = get_db_connection()
    query = """
    SELECT
        sub.subject_name,
        gi.item_name,
        gi.max_marks,
        sg.marks_obtained,
        gt.type_name
    FROM subjects sub
    JOIN sections sec ON sub.id = sec.subject_id
    JOIN section_enrollments se ON sec.id = se.section_id
    JOIN grade_items gi ON sec.id = gi.section_id
    LEFT JOIN student_grades sg ON gi.id = sg.grade_item_id AND se.student_id = sg.student_id
    JOIN grade_types gt ON gi.grade_type_id = gt.id
    WHERE se.student_id = %s AND se.semester_id = %s
    ORDER BY sub.subject_name, gt.type_name, gi.item_name
    """
    df = pd.read_sql_query(query, conn, params=(student_id, semester_id))
    conn.close()

    # If it is, we can't access df['marks_obtained'], so just return
    if df.empty:
        return df

    # Fill missing grades with a marker for display
    df['marks_obtained'] = df['marks_obtained'].astype(object).where(
        df['marks_obtained'].notnull(), 'Not Graded Yet'
    )

    return df

def get_all_days_of_week():
    """Fetches all days of the week for select boxes."""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, day_name FROM days_of_week ORDER BY id", conn)
    conn.close()
    return df.set_index('id')['day_name'].to_dict()

def get_all_time_slots():
    """Fetches all time slots for select boxes."""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, slot_name, start_time, end_time FROM time_slots ORDER BY start_time", conn)
    conn.close()
    # Format a nice display name
    df['display_name'] = df['slot_name'] + " (" + df['start_time'].astype(str) + " - " + df['end_time'].astype(str) + ")"
    return df.set_index('id')['display_name'].to_dict()

def get_schedule_for_section(section_id):
    """Fetches the current schedule for one section."""
    conn = get_db_connection()
    query = """
    SELECT cs.id, d.day_name, t.slot_name, t.start_time, t.end_time
    FROM class_schedule cs
    JOIN days_of_week d ON cs.day_id = d.id
    JOIN time_slots t ON cs.slot_id = t.id
    WHERE cs.section_id = %s
    ORDER BY d.id, t.start_time
    """
    df = pd.read_sql_query(query, conn, params=(section_id,))
    conn.close()
    return df

def add_schedule_entry(section_id, day_id, slot_id):
    """Adds a new timetable entry for a section."""
    if not all([section_id, day_id, slot_id]):
        st.error("Please select a section, day, and time slot.")
        return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO class_schedule (section_id, day_id, slot_id) VALUES (%s, %s, %s)",
            (section_id, day_id, slot_id)
        )
        conn.commit()
        st.success("Schedule entry added!")
        return True
    except psycopg2.errors.UniqueViolation:
        st.error("Error: This exact schedule slot already exists for this section.")
        conn.rollback()
        return False
    except Exception as e:
        st.error(f"An error occurred: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def remove_schedule_entry(schedule_id):
    """Removes a schedule entry by its unique ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM class_schedule WHERE id = %s", (schedule_id,))
        conn.commit()
        st.success("Schedule entry removed.")
        return True
    except Exception as e:
        st.error(f"An error occurred: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def get_teacher_schedule(teacher_id, semester_id):
    """Fetches the complete weekly timetable for a teacher."""
    conn = get_db_connection()
    query = """
    SELECT
        d.day_name,
        t.slot_name,
        t.start_time,
        t.end_time,
        sec.section_name,
        sub.subject_name
    FROM class_schedule cs
    JOIN sections sec ON cs.section_id = sec.id
    JOIN subjects sub ON sec.subject_id = sub.id
    JOIN days_of_week d ON cs.day_id = d.id
    JOIN time_slots t ON cs.slot_id = t.id
    WHERE sec.teacher_id = %s AND sec.semester_id = %s
    ORDER BY d.id, t.start_time
    """
    df = pd.read_sql_query(query, conn, params=(teacher_id, semester_id))
    conn.close()
    return df

def get_student_schedule(student_id, semester_id):
    """Fetches the complete weekly timetable for a student."""
    conn = get_db_connection()
    query = """
    SELECT
        d.day_name,
        t.slot_name,
        t.start_time,
        t.end_time,
        sec.section_name,
        sub.subject_name,
        u.username AS teacher_name
    FROM class_schedule cs
    JOIN sections sec ON cs.section_id = sec.id
    JOIN subjects sub ON sec.subject_id = sub.id
    JOIN users u ON sec.teacher_id = u.id
    JOIN days_of_week d ON cs.day_id = d.id
    JOIN time_slots t ON cs.slot_id = t.id
    JOIN section_enrollments se ON sec.id = se.section_id
    WHERE se.student_id = %s AND se.semester_id = %s
    ORDER BY d.id, t.start_time
    """
    df = pd.read_sql_query(query, conn, params=(student_id, semester_id))
    conn.close()
    return df

# --- Add these functions to database.py ---

def get_grade_types_for_teacher():
    """Fetches all grade types for the teacher's 'Add Item' form."""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, type_name FROM grade_types ORDER BY type_name", conn)
    conn.close()
    return df.set_index('id')['type_name'].to_dict()

def add_grade_item(item_name, max_marks, section_id, grade_type_id):
    """Adds a new grade item for a specific section."""
    if not all([item_name, max_marks, section_id, grade_type_id]):
        st.error("Please fill out all fields.")
        return False
    if max_marks <= 0:
        st.error("Max marks must be greater than 0.")
        return False

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO grade_items (item_name, max_marks, section_id, grade_type_id)
            VALUES (%s, %s, %s, %s)
            """,
            (item_name, max_marks, section_id, grade_type_id)
        )
        conn.commit()
        st.success(f"Grade Item '{item_name}' created.")
        return True
    except Exception as e:
        st.error(f"An error occurred: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def get_grade_items_for_section(section_id):
    """Fetches all grade items for a specific section."""
    conn = get_db_connection()
    query = """
    SELECT gi.id, gi.item_name, gi.max_marks, gt.type_name
    FROM grade_items gi
    JOIN grade_types gt ON gi.grade_type_id = gt.id
    WHERE gi.section_id = %s
    ORDER BY gt.type_name, gi.item_name
    """
    df = pd.read_sql_query(query, conn, params=(section_id,))
    conn.close()
    # Create a nice display name
    df['display_name'] = df['item_name'] + " (" + df['type_name'] + ", Max: " + df['max_marks'].astype(str) + ")"
    return df.set_index('id')['display_name'].to_dict()

def delete_grade_item(item_id):
    """Deletes a grade item and all associated student marks."""
    if not item_id:
        return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # The ON DELETE CASCADE on student_grades will handle deleting marks
        cursor.execute("DELETE FROM grade_items WHERE id = %s", (item_id,))
        conn.commit()
        st.success("Grade Item deleted.")
        return True
    except Exception as e:
        st.error(f"An error occurred: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def get_roster_for_grading(section_id, grade_item_id):
    """Fetches all students in a section and their marks for a specific item."""
    conn = get_db_connection()
    query = """
    SELECT
        s.id,
        s.student_id_str,
        b.branch_name,
        sg.marks_obtained
    FROM students s
    JOIN section_enrollments se ON s.id = se.student_id
    JOIN branches b ON s.branch_id = b.id
    LEFT JOIN student_grades sg ON s.id = sg.student_id AND sg.grade_item_id = %s
    WHERE se.section_id = %s
    ORDER BY s.student_id_str
    """
    df = pd.read_sql_query(query, conn, params=(grade_item_id, section_id))
    conn.close()
    # Rename for clarity in the data editor
    df.rename(columns={'marks_obtained': 'Marks'}, inplace=True)
    # Fill NaN with None for the data editor to show a blank cell
    df['Marks'] = df['Marks'].astype(object).where(df['Marks'].notnull(), None)
    return df

def save_student_grades(grade_item_id, marks_dict):
    """Saves student marks using an UPSERT (update or insert) operation."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Prepare data for upsert
    # We filter out 'None' values, treating them as "not entered"
    records_to_upsert = [
        (student_id, grade_item_id, marks)
        for student_id, marks in marks_dict.items()
        if marks is not None and marks != ''
    ]

    if not records_to_upsert:
        st.warning("No marks were entered to save.")
        return True

    # This is a PostgreSQL-specific "UPSERT" query
    query = """
    INSERT INTO student_grades (student_id, grade_item_id, marks_obtained)
    VALUES (%s, %s, %s)
    ON CONFLICT (student_id, grade_item_id)
    DO UPDATE SET marks_obtained = EXCLUDED.marks_obtained;
    """

    try:
        # Use executemany for efficient bulk upsert
        cursor.executemany(query, records_to_upsert)
        conn.commit()
        st.success(f"Successfully saved {len(records_to_upsert)} grade(s).")
        return True
    except Exception as e:
        st.error(f"An error occurred while saving grades: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# --- REPLACE the get_attendance_vs_grades_data function with this one ---

def get_attendance_vs_grades_data(semester_id, teacher_id=None):
    """
    Fetches a correlation-ready dataset of student attendance vs.
    their total grade percentage for every subject.
    Optionally filters by teacher_id.
    """
    conn = get_db_connection()

    # Base query with placeholders for optional filters
    query = """
    WITH
    AttendanceStats AS (
        SELECT
            a.student_id,
            a.section_id, -- <-- FIX 1: Was sec.section_id
            SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END)::FLOAT AS present_count,
            COUNT(CASE WHEN a.status IN ('Present', 'Absent') THEN 1 ELSE 0 END)::FLOAT AS total_graded_classes,
            (SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END)::FLOAT /
             NULLIF(COUNT(CASE WHEN a.status IN ('Present', 'Absent') THEN 1 ELSE 0 END)::FLOAT, 0)) * 100 AS attendance_percentage
        FROM attendance a
        JOIN sections sec ON a.section_id = sec.id
        WHERE a.semester_id = %s
          AND a.status IN ('Present', 'Absent')
          {teacher_filter_sec} -- Optional filter
        GROUP BY a.student_id, a.section_id -- <-- FIX 2: Was sec.section_id
    ),
    GradeStats AS (
        SELECT
            sg.student_id,
            gi.section_id,
            SUM(sg.marks_obtained)::FLOAT AS total_marks_obtained,
            SUM(gi.max_marks)::FLOAT AS total_max_marks,
            (SUM(sg.marks_obtained)::FLOAT /
             NULLIF(SUM(gi.max_marks)::FLOAT, 0)) * 100 AS grade_percentage
        FROM student_grades sg
        JOIN grade_items gi ON sg.grade_item_id = gi.id
        WHERE gi.section_id IN (
            SELECT id FROM sections WHERE semester_id = %s {teacher_filter_plain} -- Optional filter
        )
        GROUP BY sg.student_id, gi.section_id
    )
    SELECT
        s.student_id_str,
        s.full_name,
        sub.subject_name,
        att.attendance_percentage,
        grd.grade_percentage
    FROM
        section_enrollments se
    JOIN students s ON se.student_id = s.id
    JOIN sections sec ON se.section_id = sec.id
    JOIN subjects sub ON sec.subject_id = sub.id
    JOIN AttendanceStats att ON se.student_id = att.student_id AND se.section_id = att.section_id
    JOIN GradeStats grd ON se.student_id = grd.student_id AND se.section_id = grd.section_id
    WHERE
        se.semester_id = %s
        {teacher_filter_sec} -- Optional filter
        AND att.attendance_percentage IS NOT NULL
        AND grd.grade_percentage IS NOT NULL;
    """

    # Start with the base parameters
    params = [semester_id, semester_id, semester_id]

    # Add teacher filters if a teacher_id is provided
    if teacher_id:
        teacher_filter_sec = "AND sec.teacher_id = %s"
        teacher_filter_plain = "AND teacher_id = %s"
        # Insert the teacher_id into the correct spots in the param list
        params.insert(1, teacher_id) # For AttendanceStats
        params.insert(2, teacher_id) # For GradeStats
        params.append(teacher_id)    # For final SELECT
    else:
        teacher_filter_sec = ""
        teacher_filter_plain = ""

    # Format the query with the filter strings
    final_query = query.format(
        teacher_filter_sec=teacher_filter_sec,
        teacher_filter_plain=teacher_filter_plain
    )

    df = pd.read_sql_query(final_query, conn, params=tuple(params))
    conn.close()
    return df

def get_absence_heatmap_data(semester_id, teacher_id=None):
    """
    Counts all 'Absent' records, grouped by the subject and the day of the week.
    Optionally filters by teacher_id.
    """
    conn = get_db_connection()

    query = """
    SELECT
        sub.subject_name,
        TRIM(to_char(a.date, 'Day')) AS day_of_week,
        EXTRACT(ISODOW FROM a.date) AS day_sort_key, -- 1=Mon, 7=Sun
        COUNT(a.id) AS absence_count
    FROM
        attendance a
    JOIN
        sections sec ON a.section_id = sec.id
    JOIN
        subjects sub ON sec.subject_id = sub.id
    WHERE
        a.semester_id = %s
        AND a.status = 'Absent'
        {teacher_filter_sec} -- Optional filter
    GROUP BY
        sub.subject_name, day_of_week, day_sort_key
    ORDER BY
        sub.subject_name, day_sort_key;
    """

    params = [semester_id]

    if teacher_id:
        teacher_filter_sec = "AND sec.teacher_id = %s"
        params.append(teacher_id)
    else:
        teacher_filter_sec = ""

    final_query = query.format(teacher_filter_sec=teacher_filter_sec)

    df = pd.read_sql_query(final_query, conn, params=tuple(params))
    conn.close()
    return df

# --- Add this to the end of database.py (in the STUDENT-SPECIFIC FUNCTIONS section) ---

# --- In database.py ---
# --- REPLACE the get_student_personal_analytics function with this one ---

# --- In database.py ---
# --- REPLACE the get_student_personal_analytics function with this one ---

def get_student_personal_analytics(student_id, semester_id):
    """
    Fetches the final attendance and grade percentages for a single student,
    grouped by subject.
    """
    conn = get_db_connection()
    query = """
    WITH
    AttendanceStats AS (
        SELECT
            section_id,
            (SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END)::FLOAT /
             NULLIF(COUNT(CASE WHEN status IN ('Present', 'Absent') THEN 1 ELSE 0 END)::FLOAT, 0)) * 100 AS attendance_percentage
        FROM attendance
        WHERE semester_id = %s AND student_id = %s
        GROUP BY section_id
    ),
    GradeStats AS (
        SELECT
            gi.section_id,
            (SUM(sg.marks_obtained)::FLOAT /
             NULLIF(SUM(gi.max_marks)::FLOAT, 0)) * 100 AS grade_percentage
        FROM student_grades sg
        JOIN grade_items gi ON sg.grade_item_id = gi.id
        WHERE sg.student_id = %s
          AND gi.section_id IN (SELECT id FROM sections WHERE semester_id = %s)
        GROUP BY gi.section_id
    )
    SELECT
        sub.subject_name,
        -- --- FIX: Use simple, clean aliases with no special characters ---
        COALESCE(att.attendance_percentage, 0) AS "Attendance_Percent",
        COALESCE(grd.grade_percentage, 0) AS "Grade_Percent"
        -- --- END FIX ---
    FROM
        section_enrollments se
    JOIN sections sec ON se.section_id = sec.id
    JOIN subjects sub ON sec.subject_id = sub.id
    LEFT JOIN AttendanceStats att ON se.section_id = att.section_id
    LEFT JOIN GradeStats grd ON se.section_id = grd.section_id
    WHERE
        se.semester_id = %s AND se.student_id = %s;
    """

    # We pass the student_id and semester_id multiple times
    params = (semester_id, student_id, student_id, semester_id, semester_id, student_id)
    df = pd.read_sql_query(query, conn, params=params)

    # --- FIX: Rename the columns *after* fetching the data ---
    # This avoids all SQL placeholder conflicts.
    df.rename(columns={
        "Attendance_Percent": "Attendance (%)",
        "Grade_Percent": "Grade (%)"
    }, inplace=True)

    conn.close()
    return df

# --- ADD THESE NEW FUNCTIONS to database.py ---

# --- ADD 'cursor' AS THE FIRST ARGUMENT ---
def mark_single_student_present(cursor, student_id, section_id, semester_id):
    """
    Marks a single student as 'Present' for a given section.
    Uses an UPSERT to avoid duplicates.
    THIS FUNCTION IS DESIGNED TO BE CALLED FROM WITHIN ANOTHER TRANSACTION.
    """
    # --- REMOVE ALL conn = get_db_connection() and cursor = conn.cursor() ---
    date_str = datetime.now().strftime('%Y-%m-%d')

    # This is a PostgreSQL-specific "UPSERT" query
    query = """
    INSERT INTO attendance (student_id, section_id, semester_id, date, status)
    VALUES (%s, %s, %s, %s, 'Present')
    ON CONFLICT (student_id, section_id, date)
    DO UPDATE SET status = 'Present';
    """
    try:
        cursor.execute(query, (student_id, section_id, semester_id, date_str))
        # --- We DO NOT commit here. The CALLING function (redeem_qr_code) will commit. ---
        return date_str
    except Exception as e:
        print(f"Error in mark_single_student_present: {e}")
        # --- We DO NOT roll back here. The CALLING function will roll back. ---
        return None
    # --- REMOVE ALL cursor.close() and conn.close() ---


def create_qr_session(section_id, duration_minutes=5):
    """
    Creates a new, active attendance session for a section.
    Returns the unique UUID for the QR code.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Generate a unique string for the QR code
    session_uuid = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(minutes=duration_minutes)

    try:
        # Deactivate any old sessions for this same section
        cursor.execute("UPDATE attendance_sessions SET is_active = FALSE WHERE section_id = %s", (section_id,))

        # Insert the new session
        cursor.execute(
            """
            INSERT INTO attendance_sessions (section_id, session_uuid, expires_at, is_active)
            VALUES (%s, %s, %s, TRUE)
            """,
            (section_id, session_uuid, expires_at)
        )
        conn.commit()
        return session_uuid
    except Exception as e:
        print(f"Error creating QR session: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

# --- REPLACE THE ENTIRE redeem_qr_code FUNCTION WITH THIS ---

def redeem_qr_code(session_uuid, student_id, semester_id):
    """
    Called when a student scans a QR code.
    Validates the session and marks the student as present.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # --- 1. THIS IS THE MISSING LOGIC ---
        # Find the session from the database
        cursor.execute(
            "SELECT id, section_id, expires_at, is_active FROM attendance_sessions WHERE session_uuid = %s",
            (session_uuid,)
        )
        session_data = cursor.fetchone()

        # Check if the QR code is even valid
        if not session_data:
            conn.rollback()
            return "error", "Invalid QR Code. This session does not exist."

        session_db_id, section_id, expires_at, is_active = session_data

        # Check if it's expired or inactive
        if datetime.now() > expires_at:
            conn.rollback()
            return "error", f"QR Code has expired. This session ended at {expires_at.strftime('%H:%M:%S')}."

        if not is_active:
            conn.rollback()
            return "error", "This attendance session is no longer active."
        # --- END OF MISSING LOGIC ---

        # 3. Try to log the scan (prevents re-scanning)
        try:
            cursor.execute(
                "INSERT INTO qr_scans (session_id, student_id) VALUES (%s, %s)",
                (session_db_id, student_id) # This variable is now defined
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return "info", "Attendance already marked for this session."

        # 4. Mark the student as present
        # This calls the mark_single_student_present function we fixed earlier
        date_marked = mark_single_student_present(cursor, student_id, section_id, semester_id) # This variable is now defined

        if date_marked:
            conn.commit()
            return "success", f"Attendance successfully marked for **{date_marked}**!"
        else:
            conn.rollback()
            return "error", "Failed to save attendance. Please contact your teacher."

    except Exception as e:
        print(f"Error in redeem_qr_code: {e}") # This will print the *real* error to your terminal
        conn.rollback()
        return "error", "An unexpected error occurred."
    finally:
        cursor.close()
        conn.close()

def deactivate_qr_session(session_uuid):
    """Sets an active QR session's is_active flag to FALSE."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE attendance_sessions SET is_active = FALSE WHERE session_uuid = %s",
            (session_uuid,)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deactivating session: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()