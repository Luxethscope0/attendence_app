# send_alerts.py
import smtplib  # For sending the email
import ssl      # For a secure connection
from email.message import EmailMessage
import database as db  # To get our student list!
import os

# --- 1. EMAIL CONFIGURATION (EDIT THIS!) ---
#
# IMPORTANT: Use a "App Password" if you have 2-Factor Auth (see notes below)
#
SENDER_EMAIL = "bharatraj.16k@gmail.com"
SENDER_PASSWORD = os.environ.get("MY_APP_SENDER_PASSWORD")

if not SENDER_PASSWORD:
    print("Error: SENDER_PASSWORD environment variable not set.")
    exit()

# SMTP Server for your email provider
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # For SSL

# --- 2. THE NOTIFICATION SCRIPT ---

def send_low_attendance_alerts():
    print("Starting low attendance alert script...")

    # Get the active semester ID
    semester_id, semester_name = db.get_active_semester()
    if not semester_id:
        print("Error: No active semester found. Exiting.")
        return

    print(f"Checking for low attendance in semester: {semester_name}")

    # Get the list of students from our database function
    try:
        low_attendance_df = db.get_low_attendance_students(semester_id, threshold=75.0)
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return

    if low_attendance_df.empty:
        print("No students with low attendance. All good! Exiting.")
        return

    print(f"Found {len(low_attendance_df)} instances of low attendance.")

    # Create a secure SSL context
    context = ssl.create_default_context()

    try:
        # Log in to the email server
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            print("Successfully logged into email server.")

            # Loop through each student record and send an email
            for index, row in low_attendance_df.iterrows():
                student_name = row['full_name']
                student_email = row['email']
                subject_name = row['subject_name']
                percentage = row['attendance_percentage']

                if not student_email:
                    print(f"Skipping {student_name} for {subject_name}: No email found.")
                    continue

                # --- 3. THE EMAIL CONTENT ---
                msg = EmailMessage()
                msg['Subject'] = f"Low Attendance Warning: {subject_name}"
                msg['From'] = SENDER_EMAIL
                msg['To'] = student_email

                # Set the email body (plain text)
                msg.set_content(
                    f"Dear {student_name},\n\n"
                    f"This is an automated alert from the Attendance Management System.\n\n"
                    f"Your attendance for the subject '{subject_name}' is currently {percentage:.2f}%, "
                    f"which is below the 75% requirement.\n\n"
                    f"Please ensure you attend all future classes for this subject.\n\n"
                    f"Thank you,\n"
                    f"College Administration"
                )

                # You could also set an HTML version
                # msg.add_alternative(f"""
                # <html><body>
                # <p>Dear {student_name},</p>
                # <p>This is an automated alert...</p>
                # </body></html>
                # """, subtype='html')

                # Send the email
                server.send_message(msg)
                print(f"Successfully sent alert to {student_name} ({student_email}) for {subject_name}.")

        print("All alerts sent successfully.")

    except smtplib.SMTPException as e:
        print(f"Error: Failed to send emails. Details: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# --- 4. RUN THE SCRIPT ---
if __name__ == "__main__":
    send_low_attendance_alerts()