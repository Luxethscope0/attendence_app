# admin_ui.py (V4)
import streamlit as st
import plotly.express as px
from datetime import datetime
import database as db
import pandas as pd # Make sure pandas is imported

def render_admin_page(active_semester_id, active_semester_name):
    st.title(f"🏫 Admin Panel ({active_semester_name})")
    st.sidebar.subheader("Admin Tools")

    # --- Handle "No Active Semester" ---
    if not active_semester_id:
        st.sidebar.error("No Active Semester set.")
        st.error("There is no active semester. Please add and activate a semester to manage the app.")

        st.subheader("🎓 Manage Semesters")
        all_semesters_df = db.get_all_semesters()
        col1, col2, col3 = st.columns(3)
        with col1:
            with st.form("add_semester_form"):
                st.markdown("**Add New Semester**")
                new_sem_name = st.text_input("Semester Name (e.g., Fall 2026)")
                new_sem_start = st.date_input("Start Date", value=datetime(2026, 1, 1))
                new_sem_end = st.date_input("End Date", value=datetime(2026, 5, 31))
                submitted_add_sem = st.form_submit_button("Add Semester")
                if submitted_add_sem:
                    if db.add_new_semester(new_sem_name, new_sem_start, new_sem_end):
                        st.rerun()
        with col2:
            st.markdown("**Edit Semester**")
            sem_options_edit = all_semesters_df.set_index('id')['semester_name'].to_dict()
            if not sem_options_edit: st.write("No semesters to edit.")
            else:
                with st.form("edit_semester_form"):
                    sel_sem_name_edit = st.selectbox("Select semester to edit:", options=sem_options_edit.values(), key="edit_sem_select")
                    sem_id_to_edit = [k for k,v in sem_options_edit.items() if v == sel_sem_name_edit][0]
                    sem_details = db.get_semester_details(sem_id_to_edit)
                    edit_sem_name = st.text_input("Semester Name", value=sem_details[0])
                    edit_sem_start = st.date_input("Start Date", value=sem_details[1])
                    edit_sem_end = st.date_input("End Date", value=sem_details[2])
                    submitted_edit_sem = st.form_submit_button("Update Semester")
                    if submitted_edit_sem:
                        if db.update_semester(sem_id_to_edit, edit_sem_name, edit_sem_start, edit_sem_end):
                            st.rerun()
        with col3:
            st.markdown("**Set Active Semester**")
            sem_options_active = all_semesters_df.set_index('id')['semester_name'].to_dict()
            if not sem_options_active: st.write("No semesters to activate.")
            else:
                with st.form("set_active_semester_form"):
                    st.dataframe(all_semesters_df, width='stretch')
                    sel_sem_name_active = st.selectbox("Select semester to make active:", options=sem_options_active.values(), key="active_sem_select")
                    submitted_set_active = st.form_submit_button("Set Active")
                    if submitted_set_active:
                        sem_id_to_activate = [k for k,v in sem_options_active.items() if v == sel_sem_name_active][0]
                        if db.set_active_semester(sem_id_to_activate):
                            st.rerun()
        st.stop()

    # --- Main Tabbed Interface ---
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Dashboard",
        "📬 Requests",
        "🏫 Academic Setup",
        "🧑‍🏫 Users & Sections",
        "📈 Analytics",
        "🚫 Danger Zone"
    ])

    # --- Tab 1: Dashboard ---
    with tab1:
        st.subheader("Key Performance Indicators (Overall)")

        pending_leave, pending_enroll, pending_regs = db.get_pending_counts(active_semester_id)

        col1, col2, col3 = st.columns(3)
        col1.metric("Pending Student Registrations", f"{pending_regs}")
        col2.metric("Pending Leave Requests", f"{pending_leave}")
        col3.metric("Pending Enroll Requests", f"{pending_enroll}")

        st.markdown("---")
        st.subheader("Interactive Analytics")

        df = db.get_admin_dashboard_data(active_semester_id)

        if df.empty:
            st.warning("No attendance data recorded for this semester yet.")
        else:
            with st.expander("Filter Dashboard Data", expanded=True):
                branch_list = df['branch_name'].unique()
                subject_list = df['subject_name'].unique()
                teacher_list = df['teacher_name'].unique()

                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    selected_branches = st.multiselect("Filter by Branch:", branch_list)
                    selected_subjects = st.multiselect("Filter by Subject:", subject_list)
                with f_col2:
                    selected_teachers = st.multiselect("Filter by Teacher:", teacher_list)

            df_filtered = df.copy()

            if selected_branches:
                df_filtered = df_filtered[df_filtered['branch_name'].isin(selected_branches)]
            if selected_subjects:
                df_filtered = df_filtered[df_filtered['subject_name'].isin(selected_subjects)]
            if selected_teachers:
                df_filtered = df_filtered[df_filtered['teacher_name'].isin(selected_teachers)]

            st.markdown("#### Filtered Results")

            if df_filtered.empty:
                st.info("No data matches your filter criteria.")
            else:
                df_graded = df_filtered[df_filtered['status'].isin(['Present', 'Absent', 'Rejected'])]
                if df_graded.empty: overall_rate = 0
                else:
                    present_count = len(df_graded[df_graded['status'] == 'Present'])
                    overall_rate = (present_count / len(df_graded)) * 100

                st.metric("Attendance Rate (for Selection)", f"{overall_rate:.2f}%")

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Attendance Rate by Branch**")
                    branch_attendance = df_graded.groupby('branch_name')['status'].value_counts(normalize=True).unstack().rename(columns={'Present': 'PresentRate'})
                    if 'PresentRate' in branch_attendance.columns:
                        branch_attendance['PresentRate'] = branch_attendance['PresentRate'] * 100
                        fig_branch = px.bar(branch_attendance, y='PresentRate', x=branch_attendance.index, text_auto='.1f%')
                        st.plotly_chart(fig_branch, use_container_width=True, config={})
                    else: st.info("No 'Present' records found for this filter.")

                with c2:
                    st.markdown("**Attendance Rate by Subject**")
                    subject_attendance = df_graded.groupby('subject_name')['status'].value_counts(normalize=True).unstack().rename(columns={'Present': 'PresentRate'})
                    if 'PresentRate' in subject_attendance.columns:
                        subject_attendance['PresentRate'] = subject_attendance['PresentRate'] * 100
                        fig_subject = px.bar(subject_attendance, y='PresentRate', x=subject_attendance.index, text_auto='.1f%')
                        st.plotly_chart(fig_subject, use_container_width=True, config={})
                    else: st.info("No 'Present' records found for this filter.")

    # --- Tab 2: Requests ---
    with tab2:
        st.subheader("Review Pending Registrations")
        pending_regs_df = db.get_pending_registrations()

        if pending_regs_df.empty:
            st.info("No pending registration requests.")
        else:
            st.dataframe(pending_regs_df, width='stretch', hide_index=True)

            # --- UPDATE THIS DICTIONARY COMPREHENSION ---
            request_options = {
                row['id']: f"{row['full_name']} - {row['branch_name']}"
                for i, row in pending_regs_df.iterrows()
            }

            with st.form("approve_registration_form"):
                st.markdown("**Approve or Reject a Registration**")

                selected_request_id = st.selectbox(
                    "Select Request:",
                    options=request_options.keys(),
                    format_func=lambda id: request_options[id]
                )

                suggested_id = ""
                if selected_request_id:
                    # Call our new, clean function from database.py
                    program_id, branch_id = db.get_registration_request_details(selected_request_id)

                    if program_id and branch_id:
                        current_year = datetime.now().year
                        suggested_id = db.get_next_student_id(branch_id, program_id, current_year)
                    else:
                        suggested_id = "" # Fallback if no data

                final_student_id = st.text_input("Student ID:", value=suggested_id)
                joining_year = st.number_input("Joining Year:", value=datetime.now().year)

                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("✅ Approve", width='stretch'):
                        if not final_student_id:
                            st.error("Student ID cannot be empty.")
                        else:
                            if db.approve_registration(selected_request_id, final_student_id, joining_year):
                                st.rerun()

                with col2:
                    if st.form_submit_button("❌ Reject", type="primary", width='stretch'):
                        if db.reject_registration(selected_request_id):
                            st.rerun()

        st.markdown("---")

        st.subheader(f"Review Pending Leave Requests")
        pending_requests_df = db.get_pending_leave_requests(active_semester_id)
        if pending_requests_df.empty:
            st.info("No pending leave requests.")
        else:
            st.dataframe(pending_requests_df, width='stretch')
            colL, colR = st.columns(2)
            with colL:
                with st.form("approve_leave_form"):
                    st.markdown("**Approve/Reject a Request**")
                    request_options = pending_requests_df.set_index('id')['student_id_str'].to_dict()
                    request_options_display = {k: f"{v} (on {pending_requests_df.loc[pending_requests_df['id'] == k, 'date'].values[0]})" for k,v in request_options.items()}
                    selected_request_id = st.selectbox("Select Request:", options=request_options.keys(), format_func=lambda id: request_options_display[id])
                    if st.form_submit_button("✅ Approve"):
                        if db.update_leave_request(selected_request_id, 'Approved'):
                            st.rerun()
            with colR:
                with st.form("reject_leave_form"):
                    st.markdown("​")
                    request_options_reject = pending_requests_df.set_index('id')['student_id_str'].to_dict()
                    request_options_display_reject = {k: f"{v} (on {pending_requests_df.loc[pending_requests_df['id'] == k, 'date'].values[0]})" for k,v in request_options_reject.items()}
                    selected_request_id_reject = st.selectbox("Select Request:", options=request_options_reject.keys(), format_func=lambda id: request_options_display_reject[id], key="reject_select")
                    if st.form_submit_button("❌ Reject", type="primary"):
                        if db.update_leave_request(selected_request_id_reject, 'Rejected'):
                            st.rerun()

        with st.expander("View Leave Request History"):
            history_df = db.get_leave_request_history(active_semester_id)
            if history_df.empty: st.info("No history.")
            else: st.dataframe(history_df, width='stretch')

        st.markdown("---")

        st.subheader(f"Review Pending Enrollment Requests")
        pending_enroll_requests_df = db.get_pending_enrollment_requests(active_semester_id)

        if pending_enroll_requests_df.empty:
            st.info("No pending enrollment requests.")
        else:
            st.dataframe(pending_enroll_requests_df, width='stretch', hide_index=True)

            with st.form("approve_enroll_form"):
                st.markdown("**Approve or Reject a Request**")

                # Create display mapping
                request_options = pending_enroll_requests_df.set_index('id').to_dict('index')
                request_display_map = {
                    id: f"{row['student_id_str']} (requesting {row['requested_subject']})"
                    for id, row in request_options.items()
                }

                selected_request_id = st.selectbox(
                    "Select Request:",
                    options=request_display_map.keys(),
                    format_func=lambda id: request_display_map[id]
                )

                if selected_request_id:
                    _, subject_id = db.get_request_details_for_approval(selected_request_id)
                    available_sections = db.get_sections_for_subject(subject_id, active_semester_id)

                    if not available_sections:
                        st.error("Cannot approve: No sections exist for this subject. Please create a section first.")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.form_submit_button("✅ Approve and Enroll", disabled=True)
                        with col2:
                            if st.form_submit_button("❌ Reject", type="primary"):
                                if db.update_enrollment_request_status(selected_request_id, 'Rejected'):
                                    st.success("Request rejected.")
                                    st.rerun()
                    else:
                        selected_section_id = st.selectbox(
                            "Select Section to Enroll Student In:",
                            options=available_sections.keys(),
                            format_func=lambda id: available_sections[id]
                        )
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("✅ Approve and Enroll"):
                                student_id, _ = db.get_request_details_for_approval(selected_request_id)
                                if db.enroll_student_in_section(student_id, selected_section_id, active_semester_id):
                                    db.update_enrollment_request_status(selected_request_id, 'Approved')
                                    st.success("Student enrolled and request approved!")
                                    st.rerun()
                        with col2:
                            if st.form_submit_button("❌ Reject", type="primary"):
                                if db.update_enrollment_request_status(selected_request_id, 'Rejected'):
                                    st.success("Request rejected.")
                                    st.rerun()
                else:
                    st.write("No requests to display.")

        with st.expander("View Enrollment Request History"):
            enroll_history_df = db.get_enrollment_request_history(active_semester_id)
            if enroll_history_df.empty: st.info("No history.")
            else: st.dataframe(enroll_history_df, width='stretch', hide_index=True)

    # --- Tab 3: Academic Setup (V4) ---
    with tab3:
        st.subheader("🎓 Manage Semesters")
        # (Semester logic is unchanged)
        all_semesters_df = db.get_all_semesters()
        col1, col2, col3 = st.columns(3)
        with col1:
            with st.form("add_semester_form_tab"):
                st.markdown("**Add New Semester**")
                new_sem_name = st.text_input("Semester Name")
                new_sem_start = st.date_input("Start Date", value=datetime(2026, 1, 1))
                new_sem_end = st.date_input("End Date", value=datetime(2026, 5, 31))
                if st.form_submit_button("Add Semester"):
                    if db.add_new_semester(new_sem_name, new_sem_start, new_sem_end): st.rerun()
        with col2:
            st.markdown("**Edit Semester**")
            sem_options_edit = all_semesters_df.set_index('id')['semester_name'].to_dict()
            if not sem_options_edit: st.write("No semesters to edit.")
            else:
                with st.form("edit_semester_form_tab"):
                    sel_sem_name_edit = st.selectbox("Select semester:", options=sem_options_edit.values())
                    sem_id_to_edit = [k for k,v in sem_options_edit.items() if v == sel_sem_name_edit][0]
                    sem_details = db.get_semester_details(sem_id_to_edit)
                    edit_sem_name = st.text_input("Semester Name", value=sem_details[0])
                    edit_sem_start = st.date_input("Start Date", value=sem_details[1])
                    edit_sem_end = st.date_input("End Date", value=sem_details[2])
                    if st.form_submit_button("Update Semester"):
                        if db.update_semester(sem_id_to_edit, edit_sem_name, edit_sem_start, edit_sem_end): st.rerun()
        with col3:
            st.markdown("**Set Active Semester**")
            sem_options_active = all_semesters_df.set_index('id')['semester_name'].to_dict()
            if not sem_options_active: st.write("No semesters to activate.")
            else:
                with st.form("set_active_semester_form_tab"):
                    st.dataframe(all_semesters_df, width='stretch')
                    sel_sem_name_active = st.selectbox("Select semester:", options=sem_options_active.values())
                    if st.form_submit_button("Set Active"):
                        sem_id_to_activate = [k for k,v in sem_options_active.items() if v == sel_sem_name_active][0]
                        if db.set_active_semester(sem_id_to_activate): st.rerun()

        st.markdown("---")

        # --- NEW: V4 ACADEMIC STRUCTURE MANAGEMENT ---

        st.subheader("🏛️ Manage Academic Structure")

        # --- L1: Levels of Study ---
        st.markdown("#### L1: Levels of Study")
        st.dataframe(db.get_all_levels(), width='stretch', hide_index=True)
        l_col1, l_col2 = st.columns(2)
        with l_col1:
            with st.form("add_level_form"):
                st.markdown("**Add New Level**")
                new_level_name = st.text_input("Level Name (e.g., Undergraduate)")
                if st.form_submit_button("Add Level"):
                    if db.add_level(new_level_name): st.rerun()
        with l_col2:
            with st.form("delete_level_form"):
                st.markdown("**Delete Level**")
                levels = db.get_all_levels().set_index('id')['level_name'].to_dict()
                if not levels: st.write("No levels to delete.")
                else:
                    level_to_delete = st.selectbox("Select Level:", options=levels.keys(), format_func=lambda id: levels[id])
                    st.warning("Only delete if no programs are attached.")
                    if st.form_submit_button("Delete Level", type="primary"):
                        if db.delete_level(level_to_delete): st.rerun()

        # --- L2: Programs ---
        st.markdown("#### L2: Programs")
        st.dataframe(db.get_all_programs(), width='stretch', hide_index=True)
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            with st.form("add_program_form"):
                st.markdown("**Add New Program**")
                levels = db.get_all_levels().set_index('id')['level_name'].to_dict()
                if not levels: st.write("Create a Level first.")
                else:
                    new_prog_name = st.text_input("Program Name (e.g., Integrated M.Tech)")
                    new_prog_code = st.text_input("Program Code (e.g., i)")
                    prog_level_id = st.selectbox("Assign to Level:", options=levels.keys(), format_func=lambda id: levels[id])
                    if st.form_submit_button("Add Program"):
                        if db.add_program(new_prog_name, new_prog_code, prog_level_id): st.rerun()
        with p_col2:
            with st.form("delete_program_form"):
                st.markdown("**Delete Program**")
                programs = db.get_all_programs().set_index('id')['program_name'].to_dict()
                if not programs: st.write("No programs to delete.")
                else:
                    prog_to_delete = st.selectbox("Select Program:", options=programs.keys(), format_func=lambda id: programs[id])
                    st.warning("Only delete if no branches are attached.")
                    if st.form_submit_button("Delete Program", type="primary"):
                        if db.delete_program(prog_to_delete): st.rerun()

        # --- L3: Branches ---
        st.markdown("#### L3: Branches")
        st.dataframe(db.get_all_branches(), width='stretch', hide_index=True)
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            with st.form("add_branch_form"):
                st.markdown("**Add New Branch**")
                programs = db.get_all_programs().set_index('id')['program_name'].to_dict()
                if not programs: st.write("Create a Program first.")
                else:
                    new_branch_name = st.text_input("Branch Name (e.g., Computer Science)")
                    new_branch_code = st.text_input("Branch Code (e.g., cs)")
                    branch_prog_id = st.selectbox("Assign to Program:", options=programs.keys(), format_func=lambda id: programs[id])
                    if st.form_submit_button("Add Branch"):
                        if db.add_branch(new_branch_name, new_branch_code, branch_prog_id): st.rerun()
        with b_col2:
            with st.form("delete_branch_form"):
                st.markdown("**Delete Branch**")
                branches = db.get_all_branches().set_index('id')['branch_name'].to_dict()
                if not branches: st.write("No branches to delete.")
                else:
                    branch_to_delete = st.selectbox("Select Branch:", options=branches.keys(), format_func=lambda id: branches[id])
                    st.warning("Only delete if no subjects/students are attached.")
                    if st.form_submit_button("Delete Branch", type="primary"):
                        if db.delete_branch(branch_to_delete): st.rerun()

        st.markdown("---")

        # --- L4/L5: Subjects ---
        st.subheader("📖 Manage Subjects")
        st.dataframe(db.get_all_subjects(), width='stretch', hide_index=True)
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            with st.form("add_subject_form"):
                st.markdown("**Add New Subject**")
                branches = db.get_all_branches().set_index('id')['branch_name'].to_dict()
                if not branches: st.write("Create a Branch first.")
                else:
                    new_subj_name = st.text_input("Subject Name (e.g., Data Structures)")
                    subj_branch_id = st.selectbox("Assign to Branch:", options=branches.keys(), format_func=lambda id: branches[id])
                    subj_sem_num = st.number_input("Semester Number:", min_value=1, max_value=10, value=1)
                    if st.form_submit_button("Add Subject"):
                        if db.add_subject(new_subj_name, subj_branch_id, subj_sem_num): st.rerun()
        with s_col2:
            with st.form("delete_subject_form"):
                st.markdown("**Delete Subject**")
                subjects = db.get_all_subjects().set_index('id')['subject_name'].to_dict()
                if not subjects: st.write("No subjects to delete.")
                else:
                    subj_to_delete = st.selectbox("Select Subject:", options=subjects.keys(), format_func=lambda id: subjects[id])
                    st.warning("Only delete if no sections are attached.")
                    if st.form_submit_button("Delete Subject", type="primary"):
                        if db.delete_subject(subj_to_delete): st.rerun()

        st.markdown("---")
        st.subheader("💯 Manage Grade Types")
        st.caption("Define the categories teachers can use for grading (e.g., Assignment, Quiz, Midterm).")

        # Display existing grade types
        grade_types_df = db.get_all_grade_types()
        st.dataframe(grade_types_df, width='stretch', hide_index=True)

        g_col1, g_col2 = st.columns(2)

        with g_col1:
            with st.form("add_grade_type_form"):
                st.markdown("**Add New Grade Type**")
                new_grade_type_name = st.text_input("Type Name:", placeholder="e.g., Final Project")
                if st.form_submit_button("Add Grade Type"):
                    if db.add_grade_type(new_grade_type_name):
                        st.rerun()

        with g_col2:
            with st.form("delete_grade_type_form"):
                st.markdown("**Delete Grade Type**")
                grade_type_options = grade_types_df.set_index('id')['type_name'].to_dict()
                if not grade_type_options:
                    st.write("No grade types to delete.")
                else:
                    type_to_delete_id = st.selectbox(
                        "Select Grade Type:",
                        options=grade_type_options.keys(),
                        format_func=lambda id: grade_type_options[id]
                    )
                    st.warning("Only delete if no grade items are attached.")
                    if st.form_submit_button("Delete Grade Type", type="primary"):
                        if db.delete_grade_type(type_to_delete_id):
                            st.rerun()

        # --- END OF NEW SECTION ---

    # --- Tab 4: Users & Sections ---
    with tab4:
        st.subheader(f"Manage Teachers")
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            with st.form("add_teacher_form"):
                st.markdown("**Add New Teacher**"); new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                if st.form_submit_button("Add Teacher"):
                    if db.add_new_teacher(new_username, new_password): st.rerun()
        with t_col2:
            with st.form("delete_teacher_form"):
                st.markdown("**Delete Teacher**");
                teachers = db.get_all_teachers()
                if not teachers: st.write("No teachers to delete.")
                else:
                    sel_teacher_name_del = st.selectbox("Select Teacher:", options=teachers.values())
                    if st.form_submit_button("DELETE Teacher", type="primary"):
                        teacher_id_to_delete = [k for k, v in teachers.items() if v == sel_teacher_name_del][0]
                        if db.delete_teacher(teacher_id_to_delete): st.rerun()

        st.markdown("---")

        st.subheader(f"Manage Sections")
        with st.form("add_section_form"):
            st.markdown("**Create New Section & Auto-Enroll**")
            sec_col1, sec_col2, sec_col3 = st.columns(3)
            with sec_col1:
                section_name = st.text_input("New Section Name (e.g., CS-S1)")
            with sec_col2:
                subjects = db.get_all_subjects().set_index('id')['subject_name'].to_dict()
                selected_subject_id = st.selectbox("Assign to Subject:", options=subjects.keys(), format_func=lambda id: subjects[id])
            with sec_col3:
                teachers = db.get_all_teachers();
                selected_teacher_id = st.selectbox("Assign to Teacher:", options=teachers.keys(), format_func=lambda id: teachers[id])

            st.caption("This will auto-enroll all students from the subject's parent branch who aren't already in a section for this subject.")
            if st.form_submit_button("Create Section"):
                if db.add_new_section(section_name, selected_subject_id, selected_teacher_id, active_semester_id): st.rerun()

        st.markdown("---")

        # --- ADD THIS NEW SECTION ---
        st.subheader("🗓️ Manage Section Timetables")

        # Get data for dropdowns
        all_sections_dict = db.get_all_sections(active_semester_id)
        all_days_dict = db.get_all_days_of_week()
        all_slots_dict = db.get_all_time_slots()

        if not all_sections_dict:
            st.warning("No sections exist. Create a section above to manage its timetable.")
        else:
            col1, col2 = st.columns([1, 1])

            with col1:
                st.markdown("**Add Schedule Entry**")
                with st.form("add_schedule_form"):
                    # 1. Select Section
                    sel_section_name = st.selectbox(
                        "Select Section:",
                        options=all_sections_dict.values(),
                        key="add_sched_sec"
                    )
                    sel_section_id = [k for k,v in all_sections_dict.items() if v == sel_section_name][0]

                    # 2. Select Day
                    sel_day_id = st.selectbox(
                        "Select Day:",
                        options=all_days_dict.keys(),
                        format_func=lambda id: all_days_dict[id],
                        key="add_sched_day"
                    )

                    # 3. Select Slot
                    sel_slot_id = st.selectbox(
                        "Select Time Slot:",
                        options=all_slots_dict.keys(),
                        format_func=lambda id: all_slots_dict[id],
                        key="add_sched_slot"
                    )

                    if st.form_submit_button("Add Entry"):
                        if db.add_schedule_entry(sel_section_id, sel_day_id, sel_slot_id):
                            st.rerun()

            with col2:
                st.markdown("**View & Remove Entries**")

                # Use a different key for this selectbox
                sel_section_name_view = st.selectbox(
                    "Select Section to View:",
                    options=all_sections_dict.values(),
                    key="view_sched_sec"
                )
                sel_section_id_view = [k for k,v in all_sections_dict.items() if v == sel_section_name_view][0]

                schedule_df = db.get_schedule_for_section(sel_section_id_view)

                if schedule_df.empty:
                    st.info("This section has no schedule entries.")
                else:
                    st.dataframe(schedule_df, hide_index=True)

                    # Form to remove an entry
                    with st.form("remove_schedule_form"):
                        entry_options = schedule_df.set_index('id').apply(
                            lambda row: f"{row['day_name']} - {row['slot_name']}", axis=1
                        ).to_dict()

                        sel_entry_id = st.selectbox(
                            "Select entry to remove:",
                            options=entry_options.keys(),
                            format_func=lambda id: entry_options[id]
                        )

                        if st.form_submit_button("Remove Entry", type="primary"):
                            if db.remove_schedule_entry(sel_entry_id):
                                st.rerun()

             # --- END OF NEW SECTION ---

        st.markdown("---")

        st.subheader(f"Manage Section Enrollments")
        sections = db.get_all_sections(active_semester_id)
        if not sections: st.warning("No sections found. Create one above.")
        else:
            selected_section_name = st.selectbox("Select a Section to Manage:", options=sections.values())
            selected_section_id = [k for k, v in sections.items() if v == selected_section_name][0]
            enrolled_df, available_df = db.get_enrollment_data(selected_section_id, active_semester_id)

            with st.form("enrollment_form"):
                st.markdown(f"**Editing enrollments for: {selected_section_name}**")
                all_students_df = pd.concat([enrolled_df, available_df])

                # --- START FIX ---
                if all_students_df.empty:
                    st.info("No students are enrolled in or available for this section.")
                    all_students_options = {}
                    default_student_ids = []
                    # Disable the button if there's nothing to do
                    st.form_submit_button("Update Enrollments", disabled=True)

                else:
                    # Safely create the options dictionary
                    all_students_options = all_students_df.set_index('id')['display_name'].to_dict()

                    # Safely create the default list (handles case where no one is enrolled yet)
                    if enrolled_df.empty:
                        default_student_ids = []
                    else:
                        default_student_ids = enrolled_df['id'].tolist()

                    selected_student_ids = st.multiselect(
                        "Select students:",
                        options=all_students_options.keys(),
                        format_func=lambda id: all_students_options[id],
                        default=default_student_ids
                    )
                    if st.form_submit_button("Update Enrollments"):
                        db.update_enrollments(selected_section_id, selected_student_ids, active_semester_id)
                        st.rerun()
                # --- END FIX ---

        st.markdown("---")

        st.subheader("Manage Students")
        st.info("Note: New students should be added via the 'Requests' tab after they sign up.")
        all_students = db.get_all_students_for_admin()
        if not all_students:
            st.warning("No students found.")
        else:
            # (Student Edit/Delete forms are complex now, skipping for this step to focus on hierarchy)
            st.dataframe(all_students, width='stretch')

    # --- Tab 5: Analytics ---
    with tab5:
        st.subheader("📈 Advanced Analytics")
        st.info("This dashboard provides deeper insights by correlating different data points.")

        st.markdown("---")

        # --- Chart 1: Attendance vs. Grades ---
        st.header("Attendance vs. Grade Correlation")
        st.caption("This chart plots student attendance against their overall grade for each subject.")

        # Get the data from our new function
        corr_df = db.get_attendance_vs_grades_data(active_semester_id)

        if corr_df.empty:
            st.warning("No data available to plot. This chart requires students to have both attendance and graded marks.")
        else:
            # Create a subject filter
            subject_list = corr_df['subject_name'].unique().tolist()
            selected_subjects = st.multiselect(
                "Filter by Subject:",
                options=subject_list,
                default=subject_list
            )

            if not selected_subjects:
                st.info("Please select one or more subjects to display.")
            else:
                filtered_corr_df = corr_df[corr_df['subject_name'].isin(selected_subjects)]

                # Create the scatter plot
                fig = px.scatter(
                    filtered_corr_df,
                    x="attendance_percentage",
                    y="grade_percentage",
                    color="subject_name",  # Color points by subject
                    hover_data=['full_name', 'student_id_str'], # Show this info on hover
                    labels={
                        "attendance_percentage": "Attendance Percentage (%)",
                        "grade_percentage": "Overall Grade (%)"
                    },
                    title="Attendance vs. Grade Correlation"
                )

                # Add a trendline
                fig.update_traces(marker=dict(size=10, opacity=0.7))
                fig.add_trace(
                    px.scatter(filtered_corr_df, x="attendance_percentage", y="grade_percentage", trendline="ols")
                    .data[1]
                )

                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # --- Chart 2: Absence Heatmap ---
        st.header("Absence Heatmap")
        st.caption("This heatmap shows the total number of 'Absent' marks by subject and day of the week.")

        heatmap_df = db.get_absence_heatmap_data(active_semester_id)

        if heatmap_df.empty:
            st.warning("No 'Absent' records found to build a heatmap.")
        else:
            # We need to pivot the data to create a 2D grid
            day_order = [
                'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
            ]

            try:
                heatmap_pivot = heatmap_df.pivot_table(
                    index='subject_name',
                    columns='day_of_week',
                    values='absence_count',
                    aggfunc='sum'
                ).fillna(0) # Replace empty slots with 0 absences

                # Reorder the columns to be in the correct day-of-week order
                heatmap_pivot = heatmap_pivot.reindex(columns=day_order, fill_value=0)

                # Create the heatmap
                fig_heatmap = px.imshow(
                    heatmap_pivot,
                    labels=dict(x="Day of Week", y="Subject", color="Total Absences"),
                    x=heatmap_pivot.columns,
                    y=heatmap_pivot.index,
                    text_auto=True, # Show the numbers on the squares
                    aspect="auto",
                    color_continuous_scale='Reds' # Use a Red color scale
                )
                fig_heatmap.update_xaxes(side="top")

                st.plotly_chart(fig_heatmap, use_container_width=True)

            except Exception as e:
                st.error(f"An error occurred while creating the heatmap: {e}")
                st.dataframe(heatmap_df) # Show the raw data for debugging

        st.markdown("---")

        # --- Chart 3: At-Risk Student List ---
        st.header("🚨 At-Risk Student Monitor")
        st.caption("This table automatically flags students with both low attendance and low grades.")

        # We re-use the same data from the correlation chart
        corr_df = db.get_attendance_vs_grades_data(active_semester_id)

        if corr_df.empty:
            st.warning("No data available. This report requires students to have both attendance and graded marks.")
        else:
            # --- Define Your Thresholds ---
            col1, col2 = st.columns(2)
            att_threshold = col1.number_input("Low Attendance Threshold (%)", min_value=0, max_value=100, value=75)
            grade_threshold = col2.number_input("Low Grade Threshold (%)", min_value=0, max_value=100, value=60)

            # --- Filter the DataFrame ---
            at_risk_df = corr_df[
                (corr_df['attendance_percentage'] < att_threshold) &
                (corr_df['grade_percentage'] < grade_threshold)
            ]

            if at_risk_df.empty:
                st.success("No students are currently in the 'At-Risk' category based on these thresholds.")
            else:
                st.error(f"Found {len(at_risk_df)} instances of students at risk:")

                # Format the numbers for a cleaner display
                at_risk_df['attendance_percentage'] = at_risk_df['attendance_percentage'].map('{:,.2f}%'.format)
                at_risk_df['grade_percentage'] = at_risk_df['grade_percentage'].map('{:,.2f}%'.format)

                st.dataframe(
                    at_risk_df[['full_name', 'student_id_str', 'subject_name', 'attendance_percentage', 'grade_percentage']],
                    hide_index=True,
                    width='stretch'
                )

    # --- Tab 6: Danger Zone ---
    with tab6:
        st.subheader("🚫 Danger Zone")
        st.warning("These actions are permanent and will cascade-delete related data.")
        col5, col6 = st.columns(2)
        with col5:
            st.markdown("**Delete a Section**");
            sections_to_delete = db.get_all_sections(active_semester_id)
            if not sections_to_delete: st.write("No sections to delete.")
            else:
                with st.form("delete_section_form"):
                    sel_section_name_del = st.selectbox("Select Section:", options=sections_to_delete.values())
                    if st.form_submit_button("DELETE Section", type="primary"):
                        section_id_to_delete = [k for k, v in sections_to_delete.items() if v == sel_section_name_del][0]
                        if db.delete_section(section_id_to_delete): st.rerun()
        with col6:
            st.markdown("**Delete a Semester**");
            all_semesters = db.get_all_semesters().set_index('id')['semester_name'].to_dict()
            active_sem_id, _ = db.get_active_semester();
            semesters_to_delete = {k:v for k,v in all_semesters.items() if k != active_sem_id}
            if not semesters_to_delete: st.write("No inactive semesters to delete.")
            else:
                with st.form("delete_semester_form"):
                    sel_sem_name_del = st.selectbox("Select Inactive Semester:", options=semesters_to_delete.values())
                    if st.form_submit_button("DELETE Semester", type="primary"):
                        sem_id_to_delete = [k for k,v in semesters_to_delete.items() if v == sel_sem_name_del][0]
                        if db.delete_semester(sem_id_to_delete): st.rerun()