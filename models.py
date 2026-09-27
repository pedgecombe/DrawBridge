"""SQLAlchemy models for DrawBridge.

Five entities are stored: Raffle, Participant, TicketOrder, Ticket,
and Winner. A Raffle has many TicketOrders and many Tickets; each
TicketOrder belongs to one Participant and produces one or more
Tickets; and a closed Raffle can have at most one Winner, which links
back to the single winning Ticket.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Raffle(db.Model):
    """A single raffle: its prize, pricing, and ticket sale window."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    prize = db.Column(db.String(150), nullable=False)
    ticket_price = db.Column(db.Float, nullable=False)
    ticket_limit = db.Column(db.Integer, nullable=False)
    closing_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Active")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    orders = db.relationship("TicketOrder", backref="raffle", lazy=True)
    tickets = db.relationship("Ticket", backref="raffle", lazy=True)


class Participant(db.Model):
    """A person who has placed at least one ticket order."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))

    orders = db.relationship("TicketOrder", backref="participant", lazy=True)


class TicketOrder(db.Model):
    """One purchase of one or more tickets for a single raffle."""

    id = db.Column(db.Integer, primary_key=True)
    raffle_id = db.Column(
        db.Integer, db.ForeignKey("raffle.id"), nullable=False
    )
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participant.id"), nullable=False
    )
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    payment_status = db.Column(
        db.String(20), nullable=False, default="Pending"
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    tickets = db.relationship("Ticket", backref="order", lazy=True)


class Ticket(db.Model):
    """A single ticket. ticket_number is unique per raffle, not globally.

    The (raffle_id, ticket_number) unique constraint is what guarantees
    two participants can never be issued the same ticket number within
    the same raffle, even if their orders are created concurrently.
    """

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("ticket_order.id"), nullable=False
    )
    raffle_id = db.Column(
        db.Integer, db.ForeignKey("raffle.id"), nullable=False
    )
    ticket_number = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "raffle_id",
            "ticket_number",
            name="unique_raffle_ticket_number",
        ),
    )


class Winner(db.Model):
    """The one winning ticket drawn for a raffle.

    Both raffle_id and ticket_id are unique, so a raffle can have at
    most one Winner row and a ticket can win at most once. This is
    what makes the draw route safe to submit more than once.
    """

    id = db.Column(db.Integer, primary_key=True)
    raffle_id = db.Column(
        db.Integer, db.ForeignKey("raffle.id"), nullable=False, unique=True
    )
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id"), nullable=False, unique=True
    )
    selected_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    raffle = db.relationship("Raffle", backref=db.backref("winner", uselist=False))
    ticket = db.relationship("Ticket")
