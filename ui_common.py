# ui_common.py
import streamlit as st
import plotly.express as px
import pandas as pd

def display_dashboard(df, section_name_or_title):
    st.header(f'Displaying: {section_name_or_title}')

    if df.empty or 'Date' not in df.columns or df['Date'].isnull().all():
        st.info("No attendance records found for this selection."); return

    df_data = df.dropna(subset=['Date'])

    if df_data.empty:
        st.info("No attendance records found for this selection."); return

    total_records = len(df_data)
    total_present = len(df_data[df_data['AttendanceStatus'] == 'Present'])

    if total_records == 0:
        overall_attendance_rate = 0; total_absences = 0
    else:
        total_absences = len(df_data[~df_data['AttendanceStatus'].isin(['Present', 'Excused'])])
        total_graded_records = total_present + total_absences
        if total_graded_records == 0: overall_attendance_rate = 0
        else: overall_attendance_rate = (total_present / total_graded_records) * 100

    col1, col2, col3 = st.columns(3); col1.metric("Overall Attendance Rate", f"{overall_attendance_rate:.2f}%")
    col2.metric("Total 'Present' Records", f"{total_present:,}"); col3.metric("Total 'Absent/Rejected' Records", f"{total_absences:,}")

    st.markdown("---")
    st.header("Data Visualizations"); viz_col1, viz_col2 = st.columns(2)

    with viz_col1:
        st.subheader('Attendance Rate by Section')
        df_graded = df.dropna(subset=['AttendanceStatus'])
        df_graded = df_graded[df_graded['AttendanceStatus'] != 'Excused']
        section_attendance = df_graded.groupby('Section')['AttendanceStatus'].value_counts(normalize=True).unstack().rename(columns={'Present': 'PresentRate'})

        if 'PresentRate' in section_attendance.columns:
            section_attendance = section_attendance[['PresentRate']].sort_values(by='PresentRate', ascending=False)
            section_attendance['PresentRate'] = section_attendance['PresentRate'] * 100
            section_attendance['PresentRateText'] = section_attendance['PresentRate'].apply(lambda x: f'{x:.1f}%')
            fig_subject_bar = px.bar(section_attendance, y='PresentRate', x=section_attendance.index, text='PresentRateText')
            fig_subject_bar.update_traces(textposition='outside'); st.plotly_chart(fig_subject_bar, use_container_width=True, config={})
        else:
            st.info("No 'Present' or 'Absent' records to display.")

    with viz_col2:
        st.subheader('Absence Trend Over Time')
        absences_over_time = df_data[df_data['AttendanceStatus'].isin(['Absent', 'Rejected'])].groupby('Date').size().reset_index(name='AbsenceCount')
        fig_time_line = px.line(absences_over_time, x='Date', y='AbsenceCount'); st.plotly_chart(fig_time_line, use_container_width=True, config={})

    st.markdown("---")
    st.header('🔮 Full Attendance Log')

    log_columns = ['Date', 'Section', 'AttendanceStatus']
    if 'StudentID' in df.columns:
        log_columns.extend(['StudentID', 'Batch'])

    log_df = df_data[log_columns].sort_values(by='Date', ascending=False)
    st.dataframe(log_df, width='stretch')

# --- Add this new function to ui_common.py ---

def pivot_schedule(df):
    """Pivots a schedule DataFrame into a beautiful calendar view."""
    if df.empty:
        return df

    # Define the order of days and slots
    day_order = [
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
    ]

    # Get a sorted list of time slots from the df
    slot_order = df.sort_values('start_time')['slot_name'].unique()

    # Create the text to display in each cell
    if 'teacher_name' in df.columns:
        # Format for student view
        df['cell_display'] = df['subject_name'] + "\n(" + df['section_name'] + ")\n" + df['teacher_name']
    else:
        # Format for teacher view
        df['cell_display'] = df['subject_name'] + "\n(" + df['section_name'] + ")"

    # Pivot the table
    schedule_pivot = df.pivot_table(
        index='slot_name',
        columns='day_name',
        values='cell_display',
        aggfunc='first'
    ).fillna("") # Replace NaNs with empty strings

    # Reorder columns (days) and rows (slots)
    schedule_pivot = schedule_pivot.reindex(columns=day_order, fill_value="").loc[slot_order]

    return schedule_pivot