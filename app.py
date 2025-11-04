 # app.py (V4)
import streamlit as st
import streamlit_authenticator as stauth
import database as db
import pandas as pd

# --- Import the UI modules ---
import admin_ui
import teacher_ui
import student_ui

st.set_page_config(layout="wide")

# --- AUTHENTICATION ---
credentials, user_roles, user_ids_by_username = db.fetch_users_from_db()
authenticator = stauth.Authenticate(
    credentials=credentials, cookie_name='attendance_app_cookie',
    key='a_secret_key_for_cookie_signing', cookie_expiry_days=30
)

# --- 7. LOGGED IN / LOGGED OUT LOGIC ---

# --- IF THE USER IS LOGGED IN ---
if st.session_state["authentication_status"]:
    # --- 1. SESSION STATE SETUP ---
    name = st.session_state["name"]
    username = st.session_state["username"]
    user_role = user_roles[username]
    user_id = user_ids_by_username[username]

    st.sidebar.title(f"Welcome, {name}!");
    authenticator.logout('Logout', 'sidebar')

    active_semester_id, active_semester_name = db.get_active_semester()

    if active_semester_id:
        st.sidebar.success(f"Active Semester: **{active_semester_name}**")
    else:
        st.sidebar.error("No Active Semester!")
        if user_role != 'admin':
            st.error("There is no active semester. Please contact an admin to set one.")
            st.stop()

    # --- 2. ROLE-BASED ROUTING ---
    if user_role == 'admin':
        admin_ui.render_admin_page(active_semester_id, active_semester_name)

    elif user_role == 'teacher':
        teacher_ui.render_teacher_page(user_id, active_semester_id, active_semester_name)

    elif user_role == 'student':
        student_ui.render_student_page(user_id, active_semester_id, active_semester_name)

# --- IF THE USER IS NOT LOGGED IN ---
else:
    st.title("Attendance Management System")
    st.warning("Please log in or sign up to continue.")

    # --- NEW: Replace st.tabs with st.radio to preserve state ---
    nav_choice = st.radio(
        "Navigation",
        ["Login", "Sign Up"],
        horizontal=True,
        label_visibility="collapsed",
        key="nav_choice"
    )
    st.markdown("---")

    if nav_choice == "Login":
        authenticator.login()
        #if st.session_state["authentication_status"] is None:
        #    st.error('Username/password is incorrect')
        if st.session_state["authentication_status"] is None:
            st.info('Please enter your username and password')

    elif nav_choice == "Sign Up":
        st.subheader("New User Registration")
        st.info("Your account will be created after an administrator approves your request.")

        # Fetch data for cascading dropdowns
        levels_df, programs_df, branches_df = db.get_public_academic_structure()

        if levels_df.empty:
            st.error("Registration is currently disabled. No academic levels found.")
        else:

            # --- STEP 1: Academic Selection (OUTSIDE THE FORM) ---
            # This is the only way to allow on_change callbacks
            st.markdown("#### 1. Select Your Academic Path")

            def reset_program_and_branch():
                # Clear L2 and L3 when L1 changes
                st.session_state['signup_program'] = None
                st.session_state['signup_branch'] = None

            # L1: Level
            level_map = levels_df.set_index('id')['level_name'].to_dict()
            selected_level_id = st.selectbox(
                "Level of Study:",
                options=level_map.keys(),
                format_func=lambda id: level_map.get(id, "N/A"),
                key="signup_level",
                on_change=reset_program_and_branch # This is VALID (outside form)
            )

            # L2: Program (Filtered by L1)
            valid_programs = programs_df[programs_df['level_id'] == selected_level_id]
            program_map = valid_programs.set_index('id')['program_name'].to_dict()

            def reset_branch():
                # Clear L3 when L2 changes
                st.session_state['signup_branch'] = None

            selected_program_id = st.selectbox(
                "Program:",
                options=program_map.keys(),
                format_func=lambda id: program_map.get(id, "No options to select"),
                key="signup_program",
                on_change=reset_branch # This is VALID (outside form)
            )

            # L3: Branch (Filtered by L2)
            valid_branches = branches_df[branches_df['program_id'] == selected_program_id]
            branch_map = valid_branches.set_index('id')['branch_name'].to_dict()
            selected_branch_id = st.selectbox(
                "Branch:",
                options=branch_map.keys(),
                format_func=lambda id: branch_map.get(id, "No options to select"),
                key="signup_branch" # No on_change needed here
            )

            st.markdown("---")

            # --- STEP 2: Personal Details (INSIDE THE FORM) ---
            st.markdown("#### 2. Create Your Account")

            with st.form("signup_form"):
                full_name = st.text_input("Full Name:", placeholder="e.g., John Doe")
                email = st.text_input("Email:", placeholder="e.g., john.doe@example.com")
                #username = st.text_input("Desired Username:", placeholder="e.g., jdoe25")
                password = st.text_input("Password:", type="password")
                confirm_password = st.text_input("Confirm Password:", type="password")

                # Read the final values from session state for submission
                final_level_id = st.session_state.get('signup_level')
                final_program_id = st.session_state.get('signup_program')
                final_branch_id = st.session_state.get('signup_branch')

                if not final_level_id or not final_program_id or not final_branch_id:
                    st.warning("Please select a valid academic path above.")
                    submitted = st.form_submit_button("Submit Registration", disabled=True)
                else:
                    submitted = st.form_submit_button("Submit Registration")

                if submitted:
                    if not all([full_name, email, password]):
                        st.error("Please fill out all personal details fields.")
                    elif password != confirm_password:
                        st.error("Passwords do not match.")
                    else:
                        if db.submit_registration_request(
                            full_name,
                            email,
                            password,
                            final_level_id,
                            final_program_id,
                            final_branch_id
                        ):
                            # Clear the session state keys for dropdowns on success
                            if 'signup_level' in st.session_state: del st.session_state['signup_level']
                            if 'signup_program' in st.session_state: del st.session_state['signup_program']
                            if 'signup_branch' in st.session_state: del st.session_state['signup_branch']
                            st.rerun()