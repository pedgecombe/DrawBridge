from datetime import datetime

from app import app
from models import Raffle, db


with app.app_context():
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
            closing_date=datetime(2026, 9, 30, 23, 59),
            status="Active",
        )

        db.session.add(sample_raffle)
        db.session.commit()

        print("Sample raffle created successfully.")
    else:
        print("A raffle already exists. No sample data was added.")