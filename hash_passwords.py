import streamlit_authenticator as stauth
import psycopg2 # Import psycopg2

# --- Re-use the connection function ---
def get_db_connection():

    DB_HOST = os.environ.get("DB_HOST")
    DB_PORT = os.environ.get("DB_PORT", "5432") # Default to 5432 if not set
    DB_NAME = os.environ.get("DB_NAME")
    DB_USER = os.environ.get("DB_USER")
    DB_PASS = os.environ.get("DB_PASS")

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
        print(f"FATAL: Could not connect to PostgreSQL database. Details: {e}")
        exit()

def hash_existing_passwords():
    conn = get_db_connection() # Use new connection function
    cursor = conn.cursor()

    # Fetch all users
    cursor.execute("SELECT id, username, password FROM users")
    users = cursor.fetchall()

    print(f"Found {len(users)} users to hash.")

    hasher = stauth.Hasher()

    hashed_passwords = {}
    for user_id, username, plain_password in users:
        # Hash the plain-text password
        hashed_pass = hasher.hash(plain_password)
        hashed_passwords[user_id] = hashed_pass
        print(f"Hashed password for: {username}")

    # Update the database with the new hashed passwords
    for user_id, hashed_pass in hashed_passwords.items():
        # Use %s for placeholder
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pass, user_id))

    conn.commit() # Commit the changes
    cursor.close()
    conn.close()

    print("\nAll passwords have been securely hashed and updated in the database.")

if __name__ == "__main__":
    hash_existing_passwords()