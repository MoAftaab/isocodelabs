import os

from .database import Base, SessionLocal, engine
from .models import User
from .security import password_hash


def main():
    Base.metadata.create_all(bind=engine)
    accounts = [
        (os.getenv("BOOTSTRAP_ESTIMATOR_USERNAME", "").strip(),
         os.getenv("BOOTSTRAP_ESTIMATOR_PASSWORD", ""), "Estimator", "estimator"),
        (os.getenv("BOOTSTRAP_SALES_USERNAME", "").strip(),
         os.getenv("BOOTSTRAP_SALES_PASSWORD", ""), "Sales Head", "sales"),
    ]
    if any(not name or len(password) < 12 for name, password, _, _ in accounts):
        raise SystemExit("Set both BOOTSTRAP_*_USERNAME and unique 12+ character BOOTSTRAP_*_PASSWORD values privately.")
    with SessionLocal() as db:
        for username, password, role_name, role in accounts:
            user = db.query(User).filter_by(username=username).first()
            if user:
                user.password_hash = password_hash(password)
                user.role = role
                user.active = True
            else:
                db.add(User(username=username, display_name=role_name, role=role,
                            password_hash=password_hash(password), active=True))
        db.commit()
    print("Bootstrap accounts saved. Passwords were not printed.")


if __name__ == "__main__":
    main()
