
import os
import sys
import uuid
from datetime import datetime, timezone

# Add the app directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from manganegus_app.database import get_db_session, get_engine
from manganegus_app.models import Base, User

def init_admin():
    print("🚀 Initializing Database and creating Admin user...")
    
    # 1. Create tables
    engine = get_engine()
    print(f"📡 Using database at: {engine.url}")
    Base.metadata.create_all(engine)
    print("✅ Tables created.")

    # 2. Create Admin user
    email = "bookers1897@gmail.com"
    username = "admin"
    password = "superbowie99"

    with get_db_session() as session:
        # Check if user exists
        existing_user = session.query(User).filter_by(email=email).first()
        if existing_user:
            print(f"⚠️ User {email} already exists. Updating password and admin status...")
            existing_user.set_password(password)
            existing_user.display_name = username
            existing_user.is_admin = True
        else:
            admin_user = User(
                id=str(uuid.uuid4()),
                email=email,
                display_name=username,
                is_admin=True,
                created_at=datetime.now(timezone.utc)
            )
            admin_user.set_password(password)
            session.add(admin_user)
            print(f"✅ Admin user created: {email}")
        
        session.commit()

if __name__ == "__main__":
    init_admin()
