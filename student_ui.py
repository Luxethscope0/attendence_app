# student_ui.py (V7 - Using streamlit-qrcode-scanner)
import streamlit as st
from datetime import datetime
import database as db
import pandas as pd
import plotly.express as px
from ui_common import display_dashboard, pivot_schedule
import threading

# --- 1. IMPORT THE LIBRARY YOU INSTALLED ---
from streamlit_qrcode_scanner import qrcode_scanner

# --- 2. Create a thread-safe lock ---
_qr_lock = threading.Lock()

# --- 3. THE VIDEO_FRAME_CALLBACK IS NO LONGER NEEDED ---
# All imports for av, cv2, etc., are gone.


def render_student_page(user_id, active_semester_id, active_semester_name):
    st.title(f"🧑‍🎓 Student Portal")
    st.sidebar.subheader("Student Tools")

    student_id = db.get_student_profile(user_id)
    if not student_id:
        st.error("Could not find student profile."); st.stop()

    st.session_state.app_student_id = student_id
    st.session_state.app_semester_id = active_semester_id

    if 'scan_result_message' not in st.session_state:
        st.session_state.scan_result_message = (None, None)
    if 'is_scanning_allowed' not in st.session_state:
        st.session_state.is_scanning_allowed = True # Start in "allowed" state

    app_mode = st.sidebar.radio(
        "Select Page:",
        ('My Schedule', 'My Grades', 'View My Attendance',
         'My Enrollments', 'Request Leave', 'Scan QR')
    )

    if app_mode == 'My Schedule':
        st.subheader(f"🗓️ My Schedule ({active_semester_name})")
        schedule_df = db.get_student_schedule(student_id, active_semester_id)

        if schedule_df.empty:
            st.info("You have no classes on your schedule. Make sure you are enrolled in sections that have been scheduled.")
        else:
            schedule_pivot = pivot_schedule(schedule_df)
            st.dataframe(schedule_pivot, use_container_width=True)
            with st.expander("View as raw list"):
                st.dataframe(schedule_df, hide_index=True, use_container_width=True)

    elif app_mode == 'My Grades':
        st.subheader(f"💯 My Grades ({active_semester_name})")
        st.markdown("---")
        st.subheader("My Performance Snapshot")

        analytics_df = db.get_student_personal_analytics(student_id, active_semester_id)

        if analytics_df.empty:
            st.info("No analytics to display yet. This chart will appear once you have both attendance and grades recorded.")
        else:
            analytics_df_melted = analytics_df.melt(
                id_vars='subject_name',
                value_vars=['Attendance (%)', 'Grade (%)'],
                var_name='Metric',
                value_name='Percentage'
            )
            fig_bar = px.bar(
                analytics_df_melted,
                x="subject_name",
                y="Percentage",
                color="Metric",
                barmode="group",
                title="My Attendance vs. Grade by Subject",
                labels={"subject_name": "Subject", "Percentage": "Percentage (%)"},
                text_auto='.2f'
            )
            fig_bar.update_traces(textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        st.subheader("My Grade Details")
        grades_df = db.get_student_grades_summary(student_id, active_semester_id)

        if grades_df.empty:
            st.info("No grades have been entered for your enrolled sections yet.")
        else:
            subjects = grades_df['subject_name'].unique()
            for subject in subjects:
                with st.expander(f"**{subject}**", expanded=True):
                    subject_grades_df = grades_df[grades_df['subject_name'] == subject].copy()
                    subject_grades_df['marks_numeric'] = pd.to_numeric(subject_grades_df['marks_obtained'], errors='coerce')
                    total_obtained = subject_grades_df['marks_numeric'].sum()
                    total_max = subject_grades_df['max_marks'].sum()

                    if total_max > 0:
                        overall_percentage = (total_obtained / total_max) * 100
                        st.metric(
                            label=f"Overall for {subject}",
                            value=f"{overall_percentage:.2f}%",
                            help=f"Total: {total_obtained} / {total_max}"
                        )
                    else:
                        st.info("No graded items with max marks > 0.")

                    display_df = subject_grades_df[['type_name', 'item_name', 'marks_obtained', 'max_marks']].copy()
                    display_df['marks_obtained'] = display_df['marks_obtained'].astype(str)
                    st.dataframe(
                        display_df,
                        hide_index=True,
                        width='stretch'
                    )

    elif app_mode == 'View My Attendance':
        st.subheader(f"My Attendance Dashboard ({active_semester_name})")
        student_df_full = db.fetch_student_dashboard_data(student_id, active_semester_id)
        if student_df_full.empty or 'Section' not in student_df_full.columns:
            st.info("You are not enrolled in any sections for this semester."); st.stop()

        section_list = student_df_full['Section'].unique().tolist()
        section_options = ["All My Sections"] + section_list
        selected_section_name = st.selectbox("View Dashboard for:", section_options)

        if selected_section_name == "All My Sections":
            df_to_display = student_df_full
            title = "All My Sections"
        else:
            df_to_display = student_df_full[student_df_full['Section'] == selected_section_name]
            # --- FIX: Was 'selected_section_.name' ---
            title = selected_section_name
            if not df_to_display.empty and 'section_id' in df_to_display.columns:
                selected_section_id = df_to_display['section_id'].iloc[0]
                dates_taken_df, dates_missed_df = db.get_attendance_summary(selected_section_id)
                st.metric("Days Attendance Not Taken (Mon-Fri)", f"{len(dates_missed_df)} days")
        display_dashboard(df_to_display, title)

    elif app_mode == 'My Enrollments':
        st.subheader(f"My Enrolled Sections ({active_semester_name})")
        my_enrollments_df = db.get_student_enrollments(student_id, active_semester_id)
        if my_enrollments_df.empty:
            st.info("You are not currently enrolled in any sections.")
        else:
            st.dataframe(my_enrollments_df, width='stretch', hide_index=True)

        st.markdown("---")
        st.subheader("Enroll in My Branch Subjects")

        student_branch_id = db.get_student_branch_id(student_id)
        if not student_branch_id:
            st.error("Error: Could not find your branch ID."); st.stop()

        available_sections_df = db.get_available_sections(student_id, student_branch_id, active_semester_id)

        if available_sections_df.empty:
            st.info("No new sections are available for enrollment.")
        else:
            subject_sections = {}
            for _, row in available_sections_df.iterrows():
                subject = row['subject_name']
                display_name = f"{row['section_name']} ({row['teacher_name']})"
                section_id = row['section_id']
                if subject not in subject_sections: subject_sections[subject] = {}
                subject_sections[subject][display_name] = section_id

            with st.form("self_enroll_form"):
                selected_subject = st.selectbox("1. Select a Subject:", options=subject_sections.keys())
                if selected_subject:
                    available_sections_for_subject = subject_sections[selected_subject]
                    selected_section_display = st.selectbox("2. Select a Section:", options=available_sections_for_subject.keys())
                    if st.form_submit_button("Enroll in Section"):
                        section_to_enroll = available_sections_for_subject[selected_section_display]
                        if db.enroll_student_in_section(student_id, section_to_enroll, active_semester_id):
                            st.rerun()

        st.markdown("---")
        st.subheader("Request an Off-Branch Subject")

        off_branch_subjects = db.get_off_branch_subjects(student_branch_id, active_semester_id)

        if not off_branch_subjects:
            st.info("No off-branch subjects are available for request.")
        else:
            with st.form("request_enroll_form"):
                selected_subject_id = st.selectbox(
                    "Select a Subject to Request:",
                    options=off_branch_subjects.keys(),
                    format_func=lambda id: off_branch_subjects[id]
                )
                reason = st.text_area("Reason for request:")
                if st.form_submit_button("Submit Request"):
                    if db.submit_enrollment_request(student_id, selected_subject_id, active_semester_id, reason):
                        st.rerun()

        with st.expander("View My Off-Branch Request History"):
            request_history_df = db.get_student_enrollment_requests(student_id, active_semester_id)
            if request_history_df.empty: st.write("No requests submitted.")
            else: st.dataframe(request_history_df, width='stretch', hide_index=True)

    elif app_mode == 'Request Leave':
        st.subheader("Submit a Leave Request")
        with st.form("leave_request_form"):
            leave_date = st.date_input("Date of Absence:", datetime.now())
            leave_reason = st.text_area("Reason for Absence:")
            if st.form_submit_button("Submit Request"):
                if db.submit_leave_request(student_id, active_semester_id, leave_date, leave_reason):
                    st.rerun()
        st.markdown("---")
        st.subheader("My Past Requests")
        requests_df = db.get_student_leave_requests(student_id, active_semester_id)
        if requests_df.empty:
            st.info("You have not submitted any leave requests.")
        else:
            st.dataframe(requests_df, width='stretch')

    # --- 4. THIS IS THE 'Scan QR' BLOCK using streamlit-qrcode-scanner ---
    elif app_mode == 'Scan QR':
        st.subheader(f"📷 Scan Attendance QR Code")

        # 1. Display the result message
        status, message = st.session_state.scan_result_message
        if status == 'success':
            st.success(message)
        elif status == 'info':
            st.info(message)
        elif status == 'error':
            st.error(message)

        # 2. Only show the scanner if scanning is allowed
        if st.session_state.is_scanning_allowed:
            st.info("Point your camera at the QR Code...")

            # --- THIS IS THE NEW SCANNER FUNCTION CALL ---
            # It uses the library you installed
            qr_data = qrcode_scanner(key="streamlit_qr_scanner")

            # 3. If the scanner found data, process it
            if qr_data:
                # Use the lock just in case of a fast re-scan
                with _qr_lock:
                    if st.session_state.is_scanning_allowed: # Check again
                        # a. Stop future scans
                        st.session_state.is_scanning_allowed = False

                        print(f"QR CODE DETECTED: {qr_data}") # For your terminal

                        # b. Process the data
                        student_id = st.session_state.get('app_student_id', None)
                        semester_id = st.session_state.get('app_semester_id', None)

                        if student_id and semester_id:
                            status, message = db.redeem_qr_code(qr_data, student_id, semester_id)
                            st.session_state.scan_result_message = (status, message)
                        else:
                            st.session_state.scan_result_message = ("error", "Student ID not found. Log out and back in.")

                # Rerun to show the success/error message
                st.rerun()

        # 4. Show this message AFTER a scan is complete
        else:
            if status: # Only show if a scan has happened
                st.info("Scan complete! Press 'Reset' to scan again.")

        # 5. Reset button
        if st.button("Reset Scanner"):
            with _qr_lock:
                # Reset all state variables
                st.session_state.scan_result_message = (None, None)
                st.session_state.is_scanning_allowed = True
            st.rerun()