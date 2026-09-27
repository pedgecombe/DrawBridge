"""Automated tests backing up several rows of the traceability matrix.

Run with:  python -m pytest

Each test is named after the requirement it exercises so the mapping
back to the Assignment 2 traceability matrix is easy to follow:
  TR-05 unique ticket generation
  BR-03 control ticket availability
  BR-05 manage payment status
  BR-07 select winner / idempotent draw
  NF-03 no duplicate ticket numbers
"""

import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app  # noqa: E402
from models import Raffle, TicketOrder, Winner, db  # noqa: E402


@pytest.fixture()
def client():
    """A Flask test client backed by a fresh in-memory SQLite database."""
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        },
    )

    with flask_app.app_context():
        db.create_all()

        raffle = Raffle(
            title="Test Raffle",
            description="A raffle used for automated testing.",
            prize="Test Prize",
            ticket_price=20.00,
            ticket_limit=5,
            closing_date=datetime.now() + timedelta(days=7),
            status="Active",
        )
        db.session.add(raffle)
        db.session.commit()

        yield flask_app.test_client(), raffle.id

        db.session.remove()
        db.drop_all()


def _buy_tickets(client, raffle_id, quantity, name="Test Buyer"):
    return client.post(
        f"/raffles/{raffle_id}/order",
        data={
            "name": name,
            "email": "buyer@example.com",
            "phone": "",
            "quantity": str(quantity),
        },
        follow_redirects=True,
    )


def test_home_page_loads(client):
    """TR-01: the server starts and the home page responds."""
    test_client, _ = client
    response = test_client.get("/")
    assert response.status_code == 200


def test_unique_ticket_numbers_per_order(client):
    """TR-05 / NF-03: an order for N tickets creates N unique numbers."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=3)

    with flask_app.app_context():
        order = TicketOrder.query.first()
        numbers = sorted(t.ticket_number for t in order.tickets)
        assert numbers == [1, 2, 3]


def test_ticket_numbers_continue_across_orders(client):
    """TR-05: a second order continues numbering rather than restarting."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=2, name="Buyer One")
    _buy_tickets(test_client, raffle_id, quantity=2, name="Buyer Two")

    with flask_app.app_context():
        all_numbers = sorted(
            t.ticket_number
            for order in TicketOrder.query.all()
            for t in order.tickets
        )
        assert all_numbers == [1, 2, 3, 4]


def test_order_rejected_when_exceeding_availability(client):
    """BR-03: ordering more tickets than remain is rejected, not saved."""
    test_client, raffle_id = client
    response = _buy_tickets(test_client, raffle_id, quantity=99)

    assert b"exceeds the available tickets" in response.data
    with flask_app.app_context():
        assert TicketOrder.query.count() == 0


def test_payment_status_update(client):
    """BR-05: an order's payment status can be moved to Paid."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=1)

    with flask_app.app_context():
        order_id = TicketOrder.query.first().id

    test_client.post(
        f"/organizer/orders/{order_id}/payment",
        data={"payment_status": "Paid"},
    )

    with flask_app.app_context():
        assert db.session.get(TicketOrder, order_id).payment_status == "Paid"


def test_draw_requires_closed_raffle_and_paid_ticket(client):
    """BR-07: no winner is drawn until the raffle is closed and a
    ticket has been marked Paid."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=1)

    # Raffle is still Active and the order is still Pending: no draw.
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")
    with flask_app.app_context():
        assert Winner.query.count() == 0

    with flask_app.app_context():
        order = TicketOrder.query.first()
        order.payment_status = "Paid"
        db.session.commit()

    test_client.post(f"/organizer/raffles/{raffle_id}/close")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")

    with flask_app.app_context():
        assert Winner.query.count() == 1


def test_draw_is_idempotent(client):
    """BR-07: submitting the draw twice never creates a second winner."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=1)

    with flask_app.app_context():
        order = TicketOrder.query.first()
        order.payment_status = "Paid"
        db.session.commit()

    test_client.post(f"/organizer/raffles/{raffle_id}/close")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")

    with flask_app.app_context():
        assert Winner.query.count() == 1
