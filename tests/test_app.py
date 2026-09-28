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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DRAWBRIDGE_DATABASE_URI"] = "sqlite://"

from app import app as flask_app  # noqa: E402
from models import Participant, Raffle, TicketOrder, User, Winner, db


@pytest.fixture()
def client():
    """A Flask test client backed by a fresh in-memory SQLite database."""
    flask_app.config.update(TESTING=True)

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
    """Authenticate a participant, then submit a ticket order."""
    with client.session_transaction() as session:
        is_authenticated = "_user_id" in session

    if not is_authenticated:
        email = (
            name.lower()
            .replace(" ", ".")
            + "@example.com"
        )

        client.post(
            "/register",
            data={
                "name": name,
                "email": email,
                "password": "ParticipantPassword123",
                "confirm_password": "ParticipantPassword123",
            },
        )

    return client.post(
        f"/raffles/{raffle_id}/order",
        data={
            "name": name,
            "email": "submitted@example.com",
            "phone": "",
            "quantity": str(quantity),
        },
        follow_redirects=True,
    )


def _login_as_organizer(client):
    """Create and authenticate an organizer for protected route tests."""
    client.post("/logout")

    with flask_app.app_context():
        organizer = User(
            name="Authorized Organizer",
            email="authorized.organizer@example.com",
            role="organizer",
        )
        organizer.set_password("OrganizerPassword123")
        db.session.add(organizer)
        db.session.commit()

    return client.post(
        "/login",
        data={
            "email": "authorized.organizer@example.com",
            "password": "OrganizerPassword123",
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
    _login_as_organizer(test_client)

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
    _login_as_organizer(test_client)

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
    _login_as_organizer(test_client)

    with flask_app.app_context():
        order = TicketOrder.query.first()
        order.payment_status = "Paid"
        db.session.commit()

    test_client.post(f"/organizer/raffles/{raffle_id}/close")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")

    with flask_app.app_context():
        assert Winner.query.count() == 1


def test_user_password_is_hashed(client):
    """Passwords are stored as hashes and can be verified securely."""
    _, _ = client

    with flask_app.app_context():
        user = User(
            name="Test Participant",
            email="participant@example.com",
            role="participant",
        )
        user.set_password("SecurePassword123")

        db.session.add(user)
        db.session.commit()

        assert user.password_hash != "SecurePassword123"
        assert user.check_password("SecurePassword123")
        assert not user.check_password("WrongPassword")


def test_user_roles_are_identified(client):
    """Users can be distinguished by their assigned application role."""
    _, _ = client

    with flask_app.app_context():
        participant = User(
            name="Test Participant",
            email="participant@example.com",
            role="participant",
        )
        participant.set_password("ParticipantPassword123")

        organizer = User(
            name="Test Organizer",
            email="organizer@example.com",
            role="organizer",
        )
        organizer.set_password("OrganizerPassword123")

        db.session.add_all([participant, organizer])
        db.session.commit()

        assert not participant.is_organizer
        assert organizer.is_organizer


def test_participant_registration_creates_account_and_session(client):
    """A valid registration creates a participant and logs the user in."""
    test_client, _ = client

    response = test_client.post(
        "/register",
        data={
            "name": "New Participant",
            "email": "NEW@example.com",
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Signed in as New Participant" in response.data

    with flask_app.app_context():
        user = User.query.filter_by(email="new@example.com").one()
        assert user.role == "participant"
        assert user.password_hash != "SecurePassword123"
        assert user.check_password("SecurePassword123")

    with test_client.session_transaction() as session:
        assert "_user_id" in session


def test_registration_rejects_duplicate_email(client):
    """Registration does not create two accounts with one email."""
    test_client, _ = client

    with flask_app.app_context():
        user = User(
            name="Existing Participant",
            email="existing@example.com",
            role="participant",
        )
        user.set_password("ExistingPassword123")
        db.session.add(user)
        db.session.commit()

    response = test_client.post(
        "/register",
        data={
            "name": "Duplicate Participant",
            "email": "EXISTING@example.com",
            "password": "DifferentPassword123",
            "confirm_password": "DifferentPassword123",
        },
        follow_redirects=True,
    )

    assert b"account with that email already exists" in response.data

    with flask_app.app_context():
        assert User.query.filter_by(email="existing@example.com").count() == 1


def test_login_rejects_invalid_password(client):
    """An incorrect password does not create an authenticated session."""
    test_client, _ = client

    with flask_app.app_context():
        user = User(
            name="Existing Participant",
            email="existing@example.com",
            role="participant",
        )
        user.set_password("CorrectPassword123")
        db.session.add(user)
        db.session.commit()

    response = test_client.post(
        "/login",
        data={
            "email": "existing@example.com",
            "password": "WrongPassword",
        },
        follow_redirects=True,
    )

    assert b"Invalid email or password" in response.data

    with test_client.session_transaction() as session:
        assert "_user_id" not in session


def test_organizer_login_and_logout(client):
    """An organizer can authenticate, reach the dashboard, and log out."""
    test_client, _ = client

    with flask_app.app_context():
        organizer = User(
            name="Test Organizer",
            email="organizer@example.com",
            role="organizer",
        )
        organizer.set_password("OrganizerPassword123")
        db.session.add(organizer)
        db.session.commit()

    response = test_client.post(
        "/login",
        data={
            "email": "organizer@example.com",
            "password": "OrganizerPassword123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Organizer Dashboard" in response.data
    assert b"Signed in as Test Organizer" in response.data

    response = test_client.post("/logout", follow_redirects=True)

    assert response.status_code == 200
    assert b"Log In" in response.data

    with test_client.session_transaction() as session:
        assert "_user_id" not in session

def test_anonymous_user_is_redirected_from_organizer_dashboard(client):
    """Unauthenticated users must log in before viewing organizer data."""
    test_client, _ = client

    response = test_client.get("/organizer")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_participant_cannot_access_or_modify_organizer_data(client):
    """Participant accounts receive 403 and cannot close a raffle."""
    test_client, raffle_id = client

    test_client.post(
        "/register",
        data={
            "name": "Regular Participant",
            "email": "participant@example.com",
            "password": "ParticipantPassword123",
            "confirm_password": "ParticipantPassword123",
        },
    )

    dashboard_response = test_client.get("/organizer")
    close_response = test_client.post(
        f"/organizer/raffles/{raffle_id}/close"
    )

    assert dashboard_response.status_code == 403
    assert close_response.status_code == 403

    with flask_app.app_context():
        raffle = db.session.get(Raffle, raffle_id)
        assert raffle.status == "Active"

def test_anonymous_user_must_log_in_before_ordering(client):
    """Anonymous users are redirected to login before ticket ordering."""
    test_client, raffle_id = client

    response = test_client.get(f"/raffles/{raffle_id}/order")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_organizer_cannot_use_participant_order_route(client):
    """Organizer accounts cannot purchase participant tickets."""
    test_client, raffle_id = client
    _login_as_organizer(test_client)

    response = test_client.get(f"/raffles/{raffle_id}/order")

    assert response.status_code == 403


def test_order_is_owned_by_authenticated_participant(client):
    """A new order records its authenticated user and trusted identity."""
    test_client, raffle_id = client

    _buy_tickets(
        test_client,
        raffle_id,
        quantity=2,
        name="Account Owner",
    )

    with flask_app.app_context():
        order = TicketOrder.query.one()
        participant = Participant.query.one()
        user = User.query.filter_by(
            email="account.owner@example.com"
        ).one()

        assert order.user_id == user.id
        assert order.user.email == "account.owner@example.com"
        assert participant.name == "Account Owner"
        assert participant.email == "account.owner@example.com"
        assert participant.email != "submitted@example.com"


def test_expired_raffle_closes_and_rejects_orders(client):
    """An expired active raffle closes before accepting a new order."""
    test_client, raffle_id = client

    with flask_app.app_context():
        raffle = db.session.get(Raffle, raffle_id)
        raffle.closing_date = datetime.now() - timedelta(minutes=1)
        db.session.commit()

    response = _buy_tickets(
        test_client,
        raffle_id,
        quantity=1,
    )

    assert b"not accepting ticket orders" in response.data

    with flask_app.app_context():
        raffle = db.session.get(Raffle, raffle_id)
        assert raffle.status == "Closed"
        assert TicketOrder.query.count() == 0


def test_raffle_creation_rejects_past_closing_date(client):
    """An organizer cannot create a raffle with a past closing time."""
    test_client, _ = client
    _login_as_organizer(test_client)

    past_date = (
        datetime.now() - timedelta(days=1)
    ).isoformat(timespec="minutes")

    response = test_client.post(
        "/organizer/raffles/create",
        data={
            "title": "Expired Raffle",
            "description": "This raffle should not be created.",
            "prize": "No Prize",
            "ticket_price": "10.00",
            "ticket_limit": "100",
            "closing_date": past_date,
        },
        follow_redirects=True,
    )

    assert b"Closing date must be in the future" in response.data

    with flask_app.app_context():
        assert Raffle.query.count() == 1


def test_draw_creates_audit_record_and_completes_raffle(client):
    """A successful draw records its audit details and completes the raffle."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=2)

    with flask_app.app_context():
        order = TicketOrder.query.one()
        order.payment_status = "Paid"
        db.session.commit()

    _login_as_organizer(test_client)
    test_client.post(f"/organizer/raffles/{raffle_id}/close")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")

    with flask_app.app_context():
        raffle = db.session.get(Raffle, raffle_id)
        winner = Winner.query.one()

        assert raffle.status == "Completed"
        assert winner.eligible_ticket_count == 2
        assert winner.selection_method == "random.choice"
        assert winner.selected_by.role == "organizer"
        assert winner.selected_at is not None


def test_completed_raffle_can_be_archived(client):
    """Archiving preserves the completed raffle and winning record."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=1)

    with flask_app.app_context():
        order = TicketOrder.query.one()
        order.payment_status = "Paid"
        db.session.commit()

    _login_as_organizer(test_client)
    test_client.post(f"/organizer/raffles/{raffle_id}/close")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")
    test_client.post(f"/organizer/raffles/{raffle_id}/archive")

    with flask_app.app_context():
        raffle = db.session.get(Raffle, raffle_id)

        assert raffle.status == "Archived"
        assert raffle.archived_at is not None
        assert raffle.winner is not None
        assert Winner.query.count() == 1

def test_draw_uses_only_paid_tickets(client):
    """Pending and cancelled tickets are excluded from the draw."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=1)
    _buy_tickets(test_client, raffle_id, quantity=2)

    with flask_app.app_context():
        orders = TicketOrder.query.order_by(TicketOrder.id).all()
        paid_order = orders[0]
        cancelled_order = orders[1]

        paid_order.payment_status = "Paid"
        cancelled_order.payment_status = "Cancelled"
        db.session.commit()

        paid_order_id = paid_order.id

    _login_as_organizer(test_client)
    test_client.post(f"/organizer/raffles/{raffle_id}/close")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")

    with flask_app.app_context():
        winner = Winner.query.one()

        assert winner.eligible_ticket_count == 1
        assert winner.ticket.order_id == paid_order_id
        assert winner.ticket.order.payment_status == "Paid"


def test_invalid_payment_status_is_rejected(client):
    """Unsupported payment values are not stored."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=1)
    _login_as_organizer(test_client)

    with flask_app.app_context():
        order_id = TicketOrder.query.one().id

    test_client.post(
        f"/organizer/orders/{order_id}/payment",
        data={"payment_status": "Refunded"},
    )

    with flask_app.app_context():
        order = db.session.get(TicketOrder, order_id)
        assert order.payment_status == "Pending"


def test_payment_status_is_locked_after_draw(client):
    """Payment eligibility cannot change after winner selection."""
    test_client, raffle_id = client
    _buy_tickets(test_client, raffle_id, quantity=1)

    with flask_app.app_context():
        order = TicketOrder.query.one()
        order.payment_status = "Paid"
        db.session.commit()
        order_id = order.id

    _login_as_organizer(test_client)
    test_client.post(f"/organizer/raffles/{raffle_id}/close")
    test_client.post(f"/organizer/raffles/{raffle_id}/draw")

    test_client.post(
        f"/organizer/orders/{order_id}/payment",
        data={"payment_status": "Cancelled"},
    )

    with flask_app.app_context():
        order = db.session.get(TicketOrder, order_id)
        assert order.payment_status == "Paid"
        assert order.raffle.status == "Completed"

def test_registration_rejects_short_password(client):
    """Participant passwords must contain at least eight characters."""
    test_client, _ = client

    response = test_client.post(
        "/register",
        data={
            "name": "Short Password",
            "email": "short@example.com",
            "password": "short",
            "confirm_password": "short",
        },
        follow_redirects=True,
    )

    assert b"at least eight characters" in response.data

    with flask_app.app_context():
        assert User.query.filter_by(email="short@example.com").first() is None


def test_registration_rejects_password_mismatch(client):
    """Password confirmation must match before account creation."""
    test_client, _ = client

    response = test_client.post(
        "/register",
        data={
            "name": "Mismatch User",
            "email": "mismatch@example.com",
            "password": "SecurePassword123",
            "confirm_password": "DifferentPassword123",
        },
        follow_redirects=True,
    )

    assert b"confirmation does not match" in response.data

    with flask_app.app_context():
        assert User.query.filter_by(
            email="mismatch@example.com"
        ).first() is None


def test_exact_ticket_limit_sells_out_raffle(client):
    """The full ticket limit can be purchased but cannot be exceeded."""
    test_client, raffle_id = client

    first_response = _buy_tickets(
        test_client,
        raffle_id,
        quantity=5,
    )
    second_response = _buy_tickets(
        test_client,
        raffle_id,
        quantity=1,
    )

    assert first_response.status_code == 200
    assert b"exceeds the available tickets" in second_response.data

    with flask_app.app_context():
        orders = TicketOrder.query.all()
        assert len(orders) == 1
        assert len(orders[0].tickets) == 5


def test_organizer_creates_valid_raffle(client):
    """A valid organizer submission creates a complete raffle record."""
    test_client, _ = client
    _login_as_organizer(test_client)

    future_date = (
        datetime.now() + timedelta(days=10)
    ).isoformat(timespec="minutes")

    response = test_client.post(
        "/organizer/raffles/create",
        data={
            "title": "New Community Raffle",
            "description": "A valid automated test raffle.",
            "prize": "Gift Basket",
            "ticket_price": "12.50",
            "ticket_limit": "200",
            "closing_date": future_date,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"New Community Raffle" in response.data

    with flask_app.app_context():
        raffle = Raffle.query.filter_by(
            title="New Community Raffle"
        ).one()

        assert raffle.prize == "Gift Basket"
        assert raffle.ticket_price == 12.50
        assert raffle.ticket_limit == 200
        assert raffle.status == "Active"