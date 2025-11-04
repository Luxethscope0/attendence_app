# teacher_ui.py (V4)
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import database as db
import qrcode
import io
import time
from ui_common import display_dashboard, pivot_schedule
from streamlit.runtime.scriptrunner import RerunException
from datetime import datetime, timedelta

def render_teacher_page(user_id, active_semester_id, active_semester_name):

    st.sidebar.subheader("Teacher Tools")
    teacher_sections = db.get_teacher_sections(user_id, active_semester_id)
    if not teacher_sections:
        app_mode = st.sidebar.radio("Select Page:", ('My Schedule',))
        st.warning(f"You are not assigned to any sections for the '{active_semester_name}' semester.")
    else:
        # --- Add 'Gradebook' to this list ---
        app_mode = st.sidebar.radio("Select Page:",
            ('My Schedule', 'View Dashboard', 'Take Attendance', 'Student Lookup',
             'Attendance Log', 'Gradebook', '📈 Analytics', 'QR Attendance')
        )

    # --- Add this new 'elif' block at the beginning ---
    if app_mode == 'My Schedule':
        st.title(f"🗓️ My Schedule ({active_semester_name})")
        schedule_df = db.get_teacher_schedule(user_id, active_semester_id)

        if schedule_df.empty:
            st.warning("Your schedule is empty. Please contact an admin to have your sections scheduled.")
        else:
            # Use the new pivot function
            schedule_pivot = pivot_schedule(schedule_df)
            st.dataframe(schedule_pivot, use_container_width=True)

            with st.expander("View as raw list"):
                st.dataframe(schedule_df, hide_index=True, use_container_width=True)

    elif app_mode == 'View Dashboard':
        st.title(f"📊 Dashboard")
        section_options = {"0": "All Sections", **teacher_sections}
        section_display_name = st.selectbox(f"Select Section:", options=section_options.values())
        selected_section_id_str = [k for k, v in section_options.items() if v == section_display_name][0]

        teacher_df = db.fetch_teacher_dashboard_data(user_id, active_semester_id)

        if selected_section_id_str == "0": df_to_display = teacher_df
        else: df_to_display = teacher_df[teacher_df['Section'] == section_display_name]
        display_dashboard(df_to_display, section_display_name)

    elif app_mode == 'Take Attendance':
        st.title("📝 Take Attendance")

        # --- 1. Initialize session state ---
        if 'editor_key' not in st.session_state:
            st.session_state.editor_key = 0
        if 'mark_all_status' not in st.session_state:
            st.session_state.mark_all_status = None

        # --- 2. Selections (Outside form) ---
        # We use the editor_key to force these to refresh after a successful save
        section_display_name = st.selectbox("Select Section:", options=teacher_sections.values(), key=f"sel_section_{st.session_state.editor_key}")
        selected_section_id = [k for k, v in teacher_sections.items() if v == section_display_name][0]
        selected_date = st.date_input("Select Date:", datetime.now(), key=f"sel_date_{st.session_state.editor_key}")
        date_str = selected_date.strftime('%Y-%m-%d')

        st.subheader(f"Roster for {section_display_name} on {date_str}")

        # --- 3. 'Mark All' buttons (MOVED OUTSIDE the form) ---
        col1, col2 = st.columns(2)

        if col1.button("Mark All Present"):
            st.session_state.mark_all_status = 'Present'
            st.rerun() # Force a rerun to apply the state

        if col2.button("Mark All Absent"):
            st.session_state.mark_all_status = 'Absent'
            st.rerun() # Force a rerun to apply the state

        # --- 4. START THE FORM ---
        with st.form("save_attendance_form"):

            roster_df = db.get_roster_with_attendance(selected_section_id, date_str)

            if roster_df.empty:
                st.warning(f"There are no students enrolled in '{section_display_name}'.")
                st.form_submit_button("💾 Save Attendance", disabled=True)
            else:
                uneditable_mask = roster_df['status'].isin(['Excused', 'Pending', 'Rejected'])

                # --- 5. Apply the 'Mark All' state (if it exists) ---
                if st.session_state.mark_all_status == 'Present':
                    roster_df.loc[~uneditable_mask, 'status'] = 'Present'
                elif st.session_state.mark_all_status == 'Absent':
                    roster_df.loc[~uneditable_mask, 'status'] = 'Absent'

                # --- 6. The Data Editor ---
                # The key MUST be unique to the data *and* the mark_all_status
                # to prevent state-clobbering
                editor_unique_key = f"attendance_editor_{selected_section_id}_{date_str}_{st.session_state.mark_all_status}_{st.session_state.editor_key}"

                edited_df = st.data_editor(
                    roster_df,
                    key=editor_unique_key, # Use the complex key
                    column_config={
                        "id": None,
                        "student_id_str": "Student ID",
                        "batch": "Branch",
                        "status": st.column_config.SelectboxColumn("Status", options=["Present", "Absent", "Excused", "Pending", "Rejected"], required=True)
                    },
                    hide_index=True, width='stretch', disabled=uneditable_mask
                )

                # --- 7. The *only* submit button ---
                if st.form_submit_button("💾 Save Attendance"):
                    if not edited_df.empty:
                        clean_df = edited_df[~edited_df['status'].isin(['Excused', 'Pending', 'Rejected'])]
                        attendance_dict = pd.Series(
                            clean_df.status.values,
                            index=clean_df.id
                        ).to_dict()

                        if db.save_attendance(selected_section_id, selected_date, attendance_dict, active_semester_id):
                            # --- 8. FIX: Clear state ONLY after successful save ---
                            st.session_state.mark_all_status = None
                            st.session_state.editor_key += 1
                            st.rerun()
                    else:
                        st.warning("No data to save.")

    elif app_mode == 'Student Lookup':
        st.title("🔎 Smart Student Lookup")
        sections = {"0": "All Sections", **db.get_teacher_sections(user_id, active_semester_id)}
        subjects = {"0": "All Subjects", **db.get_teacher_subjects_list(user_id, active_semester_id)}
        branches = {"0": "All Branches", **db.get_teacher_branches_list(user_id, active_semester_id)}

        with st.form("lookup_form"):
            selected_date = st.date_input("Select Date (Mandatory):", datetime.now())
            st.subheader("Optional Filters")
            sel_section_name = st.selectbox("Filter by Section:", options=sections.values())
            sel_subject_name = st.selectbox("Filter by Subject:", options=subjects.values())
            sel_branch_name = st.selectbox("Filter by Branch:", options=branches.values())
            sel_student_id = st.text_input("Filter by Student ID:")

            if st.form_submit_button("Search"):
                section_id = [k for k,v in sections.items() if v == sel_section_name][0]
                subject_id = [k for k,v in subjects.items() if v == sel_subject_name][0]
                branch_id = [k for k,v in branches.items() if v == sel_branch_name][0]
                results_df = db.smart_student_lookup(
                    teacher_id = user_id, date_str = selected_date.strftime('%Y-%m-%d'),
                    semester_id = active_semester_id,
                    section_id = int(section_id) if section_id != "0" else None,
                    subject_id = int(subject_id) if subject_id != "0" else None,
                    branch_id = int(branch_id) if branch_id != "0" else None,
                    student_id_str = sel_student_id.strip() if sel_student_id else None
                )
                st.subheader("Search Results")
                if results_df.empty: st.info("No records found.")
                else: st.dataframe(results_df, width='stretch', hide_index=True)

    elif app_mode == 'Attendance Log':
        st.title("📊 Attendance Log")
        if not teacher_sections: st.warning("No sections assigned."); st.stop()

        section_display_name = st.selectbox("Select Section to Audit:", options=teacher_sections.values())
        selected_section_id = [k for k, v in teacher_sections.items() if v == section_display_name][0]

        st.subheader("Quick Date Check")
        with st.form("check_date_form"):
            selected_date_check = st.date_input("Select Date to Check:", datetime.now())
            submitted_check = st.form_submit_button("Check Status")
            if submitted_check:
                date_str_check = selected_date_check.strftime('%Y-%m-%d')
                is_taken = db.check_date_status(selected_section_id, date_str_check)
                if is_taken: st.success(f"✅ Attendance WAS taken for this section on {date_str_check}.")
                else: st.error(f"❌ Attendance was NOT taken for this section on {date_str_check}.")

        st.markdown("---")

        st.subheader("Full Log Audit")
        if st.button("Generate Full Log"):
            dates_taken_df, dates_missed_df = db.get_attendance_summary(selected_section_id)
            if dates_taken_df.empty and dates_missed_df.empty:
                st.warning("No attendance has ever been taken for this subject.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    with st.expander(f"✅ Dates Taken ({len(dates_taken_df)})", expanded=True):
                        if dates_taken_df.empty: st.write("None.")
                        else: st.dataframe(dates_taken_df, hide_index=True, width='stretch')
                with col2:
                    with st.expander(f"❌ Dates Missed ({len(dates_missed_df)})", expanded=True):
                        if dates_missed_df.empty: st.write("None.")
                        else: st.dataframe(dates_missed_df, hide_index=True, width='stretch')

    elif app_mode == 'Gradebook':
        st.title(f"💯 Gradebook ({active_semester_name})")

        # 1. Select a Section
        section_display_name = st.selectbox("Select Section:", options=teacher_sections.values(), key="grade_sec_select")
        selected_section_id = [k for k, v in teacher_sections.items() if v == section_display_name][0]

        st.markdown("---")

        col1, col2 = st.columns(2)

        # 2. Form to Create New Grade Item
        with col1:
            with st.form("create_grade_item_form"):
                st.subheader("Create New Grade Item")
                item_name = st.text_input("Item Name:", placeholder="e.g., Assignment 1")
                max_marks = st.number_input("Max Marks:", min_value=1, value=20)

                # Fetch grade types for dropdown
                grade_types = db.get_grade_types_for_teacher()
                grade_type_id = st.selectbox(
                    "Grade Type:",
                    options=grade_types.keys(),
                    format_func=lambda id: grade_types[id]
                )

                if st.form_submit_button("Create Item"):
                    if db.add_grade_item(item_name, max_marks, selected_section_id, grade_type_id):
                        st.rerun()

        # 3. Form to Delete Existing Grade Item
        with col2:
            st.subheader("Manage Existing Items")
            grade_items = db.get_grade_items_for_section(selected_section_id)
            if not grade_items:
                st.info("No grade items created for this section yet.")
            else:
                with st.form("delete_grade_item_form"):
                    item_to_delete_id = st.selectbox(
                        "Select Item to Delete:",
                        options=grade_items.keys(),
                        format_func=lambda id: grade_items[id]
                    )
                    st.warning("This will delete the item and all associated student marks.")
                    if st.form_submit_button("Delete Item", type="primary"):
                        if db.delete_grade_item(item_to_delete_id):
                            st.rerun()

        st.markdown("---")
        st.subheader("Enter Student Marks")

        # 4. Select Grade Item to Enter Marks
        if not grade_items:
            st.info("Create a grade item above to begin entering marks.")
        else:
            selected_item_id = st.selectbox(
                "Select Item to Grade:",
                options=grade_items.keys(),
                format_func=lambda id: grade_items[id],
                key="select_item_to_grade"
            )

            # Get max marks for validation
            max_marks_for_item = float(db.get_grade_items_for_section(selected_section_id)[selected_item_id].split(", Max: ")[1].replace(")", ""))
            st.info(f"You are entering marks for: **{grade_items[selected_item_id]}**. Max Marks: **{max_marks_for_item}**")

            # 5. Form to Save Marks
            with st.form("save_grades_form"):
                # Get the roster with current marks
                grading_roster_df = db.get_roster_for_grading(selected_section_id, selected_item_id)

                if grading_roster_df.empty:
                    st.warning("No students are enrolled in this section.")
                else:
                    # Use data editor to enter marks
                    edited_df = st.data_editor(
                        grading_roster_df,
                        column_config={
                            "id": None, # Hide the student ID
                            "student_id_str": "Student ID",
                            "branch_name": "Branch",
                            "Marks": st.column_config.NumberColumn(
                                "Marks",
                                help=f"Enter marks out of {max_marks_for_item}",
                                min_value=0.0,
                                max_value=max_marks_for_item,
                                step=0.5,
                                format="%.2f", # 2 decimal places
                            )
                        },
                        hide_index=True,
                        use_container_width=True,
                        disabled=["student_id_str", "branch_name"] # Make student info read-only
                    )

                    if st.form_submit_button("💾 Save Marks"):
                        # Convert the edited DataFrame to a dict for saving
                        # We use the original 'id' column as the key
                        marks_dict = pd.Series(
                            edited_df.Marks.values,
                            index=edited_df.id
                        ).to_dict()

                        if db.save_student_grades(selected_item_id, marks_dict):
                            st.rerun()

    elif app_mode == '📈 Analytics':
        st.title(f"📈 Analytics ({active_semester_name})")
        st.info("This dashboard shows analytics for *your sections only*.")

        st.markdown("---")

        # --- Chart 1: Attendance vs. Grades ---
        st.header("Attendance vs. Grade Correlation")
        st.caption("This chart plots your students' attendance against their overall grade for each subject.")

        # --- FIX: Pass the 'user_id' (which is the teacher_id) ---
        corr_df = db.get_attendance_vs_grades_data(active_semester_id, teacher_id=user_id)

        if corr_df.empty:
            st.warning("No data available to plot. This chart requires students to have both attendance and graded marks.")
        else:
            # (The rest of this block is an exact copy from admin_ui.py)
            subject_list = corr_df['subject_name'].unique().tolist()
            selected_subjects = st.multiselect(
                "Filter by Subject:",
                options=subject_list,
                default=subject_list,
                key="teacher_analytics_subject_filter" # Added a unique key
            )

            if not selected_subjects:
                st.info("Please select one or more subjects to display.")
            else:
                filtered_corr_df = corr_df[corr_df['subject_name'].isin(selected_subjects)]

                fig = px.scatter(
                    filtered_corr_df,
                    x="attendance_percentage",
                    y="grade_percentage",
                    color="subject_name",
                    hover_data=['full_name', 'student_id_str'],
                    labels={
                        "attendance_percentage": "Attendance Percentage (%)",
                        "grade_percentage": "Overall Grade (%)"
                    },
                    title="Attendance vs. Grade Correlation (Your Sections)"
                )

                fig.update_traces(marker=dict(size=10, opacity=0.7))
                fig.add_trace(
                    px.scatter(filtered_corr_df, x="attendance_percentage", y="grade_percentage", trendline="ols")
                    .data[1]
                )

                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # --- Chart 2: Absence Heatmap ---
        st.header("Absence Heatmap")
        st.caption("This heatmap shows 'Absent' marks for your sections by day of the week.")

        # --- FIX: Pass the 'user_id' (which is the teacher_id) ---
        heatmap_df = db.get_absence_heatmap_data(active_semester_id, teacher_id=user_id)

        if heatmap_df.empty:
            st.warning("No 'Absent' records found to build a heatmap.")
        else:
            # (The rest of this block is an exact copy from admin_ui.py)
            day_order = [
                'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
            ]

            try:
                heatmap_pivot = heatmap_df.pivot_table(
                    index='subject_name',
                    columns='day_of_week',
                    values='absence_count',
                    aggfunc='sum'
                ).fillna(0)

                heatmap_pivot = heatmap_pivot.reindex(columns=day_order, fill_value=0)

                fig_heatmap = px.imshow(
                    heatmap_pivot,
                    labels=dict(x="Day of Week", y="Subject", color="Total Absences"),
                    x=heatmap_pivot.columns,
                    y=heatmap_pivot.index,
                    text_auto=True,
                    aspect="auto",
                    color_continuous_scale='Reds'
                )
                fig_heatmap.update_xaxes(side="top")

                st.plotly_chart(fig_heatmap, use_container_width=True)

            except Exception as e:
                st.error(f"An error occurred while creating the heatmap: {e}")
                st.dataframe(heatmap_df)

        st.markdown("---")

        # --- Chart 3: At-Risk Student List ---
        st.header("🚨 At-Risk Student Monitor")
        st.caption("This table automatically flags students in your sections with low attendance and grades.")

        corr_df = db.get_attendance_vs_grades_data(active_semester_id, teacher_id=user_id)

        if corr_df.empty:
            st.warning("No data available. This report requires students to have both attendance and graded marks.")
        else:
            # (The rest of this block is an exact copy from admin_ui.py)
            col1, col2 = st.columns(2)
            att_threshold = col1.number_input("Low Attendance Threshold (%)", min_value=0, max_value=100, value=75, key="teacher_att_thresh")
            grade_threshold = col2.number_input("Low Grade Threshold (%)", min_value=0, max_value=100, value=60, key="teacher_grade_thresh")

            at_risk_df = corr_df[
                (corr_df['attendance_percentage'] < att_threshold) &
                (corr_df['grade_percentage'] < grade_threshold)
            ]

            if at_risk_df.empty:
                st.success("No students are currently in the 'At-Risk' category based on these thresholds.")
            else:
                st.error(f"Found {len(at_risk_df)} instances of students at risk:")

                at_risk_df['attendance_percentage'] = at_risk_df['attendance_percentage'].map('{:,.2f}%'.format)
                at_risk_df['grade_percentage'] = at_risk_df['grade_percentage'].map('{:,.2f}%'.format)

                st.dataframe(
                    at_risk_df[['full_name', 'student_id_str', 'subject_name', 'attendance_percentage', 'grade_percentage']],
                    hide_index=True,
                    width='stretch'
                )

    elif app_mode == 'QR Attendance':
        st.title("📷 QR Code Attendance")

        # Initialize session state for the QR code
        if 'qr_session_uuid' not in st.session_state:
            st.session_state.qr_session_uuid = None
            st.session_state.qr_section_id = None
            st.session_state.qr_expires_at = None

        # --- A. FORM TO CREATE A NEW SESSION ---
        st.subheader("Generate a New QR Session")

        with st.form("generate_qr_form"):
            section_display_name = st.selectbox(
                "Select Section:",
                options=teacher_sections.values(),
                key="qr_sec_select"
            )
            duration = st.slider(
                "Session Duration (minutes):",
                min_value=1,
                max_value=15,
                value=5
            )

            if st.form_submit_button("Start Session"):
                selected_section_id = [k for k, v in teacher_sections.items() if v == section_display_name][0]

                # Deactivate any old session first
                st.session_state.qr_session_uuid = None

                # Create a new session in the DB
                session_uuid = db.create_qr_session(selected_section_id, duration)

                if session_uuid:
                    st.session_state.qr_session_uuid = session_uuid
                    st.session_state.qr_section_id = selected_section_id
                    st.session_state.qr_expires_at = datetime.now() + timedelta(minutes=duration)
                    st.rerun() # Rerun to show the QR code
                else:
                    st.error("Failed to create a QR session.")

        st.markdown("---")

        # --- B. DISPLAY THE ACTIVE QR CODE ---
        if st.session_state.qr_session_uuid:
            st.subheader("Active Session")

            # 1. Generate the QR Code Image
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(st.session_state.qr_session_uuid)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Save image to a byte buffer
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            # 2. Display the Image
            st.image(img_bytes, caption="Students: Scan this code with the app.")

            # 3. Display the countdown timer
            time_left = st.session_state.qr_expires_at - datetime.now()

            if time_left.total_seconds() > 0:
                # Format time as MM:SS
                minutes, seconds = divmod(int(time_left.total_seconds()), 60)
                countdown_text = f"Expires in: **{minutes:02}:{seconds:02}**"

                st.info(countdown_text)

                # Deactivate session in DB
                if st.button("Deactivate Session Now"):
                    # We don't have a DB function for this, but we can clear the state
                    db.deactivate_qr_session(st.session_state.qr_session_uuid)
                    st.session_state.qr_session_uuid = None
                    st.session_state.qr_section_id = None
                    st.session_state.qr_expires_at = None
                    st.rerun()

                # Auto-refresh the page every 5 seconds to update the timer
                time.sleep(1)
                st.rerun()

            else:
                st.warning("This session has expired.")
                # Clear the state
                st.session_state.qr_session_uuid = None
                st.session_state.qr_section_id = None
                st.session_state.qr_expires_at = None
                if st.button("Clear Expired Session"):
                    st.rerun()