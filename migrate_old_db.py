# migrate_old_db.py

"""
One-off migration script to bring an old booking.db up to the new schema:

- Adds new columns to 'users' and 'properties' tables if missing
- Hashes any plaintext passwords with bcrypt via passlib
- Normalizes missing site_role to 'standard'

Run with:
    (myenv) python migrate_old_db.py
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from security import get_password_hash


def column_exists(table_name: str, column_name: str) -> bool:
    """
    Uses SQLite PRAGMA table_info to check if a column exists.
    """
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        for row in result:
            if row["name"] == column_name:
                return True
    return False


def add_column_if_missing(table: str, column_def: str):
    """
    Adds a column to a table if it doesn't exist.
    column_def is full "COLUMN_NAME TYPE ..." fragment.
    """
    col_name = column_def.split()[0]
    if column_exists(table, col_name):
        print(f"[OK] Column '{col_name}' already exists on '{table}'.")
        return
    alter_sql = f"ALTER TABLE {table} ADD COLUMN {column_def};"
    print(f"[MIGRATE] Adding column on '{table}': {column_def}")
    with engine.connect() as conn:
        conn.execute(text(alter_sql))
        conn.commit()


def migrate_schema():
    """
    Add missing columns required by the new code.
    """
    print("=== SCHEMA MIGRATION ===")

    # --- users table ---
    # password column for hashed password storage
    add_column_if_missing("users", "password VARCHAR(128)")

    # site_role column: standard / site_owner / site_admin
    # (nullable allowed, we'll fill values in data migration)
    add_column_if_missing("users", "site_role VARCHAR(50)")

    # --- properties table ---
    # new fields: amenities / capacity / property_type
    add_column_if_missing("properties", "amenities VARCHAR(255)")
    add_column_if_missing("properties", "capacity INTEGER")
    add_column_if_missing("properties", "property_type VARCHAR(50)")

    print("=== SCHEMA MIGRATION DONE ===\n")


def migrate_data():
    """
    Hash plaintext passwords, normalize site_role.
    """
    print("=== DATA MIGRATION ===")
    db: Session = SessionLocal()

    try:
        # 1) Fix user passwords + site_role
        users = db.execute(text("SELECT id, username, password, site_role FROM users")).mappings().all()
        print(f"[INFO] Found {len(users)} users in DB.")

        for row in users:
            user_id = row["id"]
            username = row["username"]
            password = row["password"]
            site_role = row["site_role"]

            needs_update = False
            new_password = password
            new_site_role = site_role

            # If password is NULL or empty, we can't recover it.
            # We'll leave it as-is; you can reset manually later if needed.
            if password:
                # If it doesn't contain '$', it's very likely plaintext, not bcrypt.
                if "$" not in password:
                    print(f"[PASSWORD] Hashing plaintext password for user '{username}' (id={user_id})")
                    new_password = get_password_hash(password)
                    needs_update = True
            else:
                print(f"[WARN] User '{username}' (id={user_id}) has no password set.")

            # Normalize site_role
            if not site_role or site_role.strip() == "":
                print(f"[ROLE] Setting missing site_role to 'standard' for user '{username}' (id={user_id})")
                new_site_role = "standard"
                needs_update = True

            if needs_update:
                db.execute(
                    text(
                        "UPDATE users SET password = :password, site_role = :site_role WHERE id = :id"
                    ),
                    {
                        "password": new_password,
                        "site_role": new_site_role,
                        "id": user_id,
                    },
                )

        db.commit()
        print("=== DATA MIGRATION DONE ===")

    finally:
        db.close()


if __name__ == "__main__":
    print("Starting DB migration for booking.db ...")
    migrate_schema()
    migrate_data()
    print("Migration complete. You can now run:  python main.py")
