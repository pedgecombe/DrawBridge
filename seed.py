import os
from datetime import datetime, timedelta

from app import app
from models import Raffle, User, db


with app.app_context():
    db.create_all()

    organizer_email = "organizer@drawbridge.local"
    organizer_password = os.environ.get(
        "DRAWBRIDGE_ORGANIZER_PASSWORD"
    )

    if not organizer_password:
        raise SystemExit(
            "Set DRAWBRIDGE_ORGANIZER_PASSWORD before running seed.py."
        )

    existing_organizer = User.query.filter_by(
        email=organizer_email
    ).first()

    if existing_organizer is None:
        organizer = User(
            name="DrawBridge Organizer",
            email=organizer_email,
            role="organizer",
        )
        organizer.set_password(organizer_password)
        db.session.add(organizer)
        print("Organizer account created successfully.")
    else:
        print("Organizer account already exists.")

    existing_raffle = Raffle.query.first()

    if existing_raffle is None:
        sample_raffle = Raffle(
            title="Community Fundraiser Raffle",
            description=(
                "Support local community programs for a chance "
                "to win our featured prize."
            ),
            prize="Weekend Getaway Package",
            ticket_price=10.00,
            ticket_limit=500,
            closing_date=datetime.now() + timedelta(days=30),
            status="Active",
        )

        db.session.add(sample_raffle)
        print("Sample raffle created successfully.")
    else:
        print("Sample raffle already exists.")

    db.session.commit()