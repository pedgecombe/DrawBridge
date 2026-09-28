"""DrawBridge Flask application.

Defines the routes for the participant-facing pages (browsing raffles,
buying tickets, viewing confirmations) and the organizer-facing pages
(creating raffles, managing payment status, closing sales, and drawing
a winner).
"""

import os
import random
from datetime import datetime
from functools import wraps

from flask import Flask, abort, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from models import Participant, Raffle, Ticket, TicketOrder, User, Winner, db

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "DRAWBRIDGE_SECRET_KEY",
    "drawbridge-local-development-key",
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///drawbridge.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    """Load the authenticated user from the session identifier."""
    return db.session.get(User, int(user_id))


def organizer_required(view_function):
    """Allow access only to authenticated organizer accounts."""

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_organizer:
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view


def participant_required(view_function):
    """Allow access only to authenticated participant accounts."""

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role != "participant":
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view

@app.before_request
def close_expired_raffles():
    """Close active raffles once their configured closing time passes."""
    expired_raffles = Raffle.query.filter(
        Raffle.status == "Active",
        Raffle.closing_date <= datetime.now(),
    ).all()

    if not expired_raffles:
        return

    for raffle in expired_raffles:
        raffle.status = "Closed"

    db.session.commit()


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create a participant account and begin an authenticated session."""
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            error = "Name, email, and password are required."
        elif len(password) < 8:
            error = "Password must contain at least eight characters."
        elif password != confirm_password:
            error = "The password confirmation does not match."
        elif User.query.filter_by(email=email).first() is not None:
            error = "An account with that email already exists."
        else:
            user = User(
                name=name,
                email=email,
                role="participant",
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()
            login_user(user)

            return redirect(url_for("home"))

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate an existing participant or organizer."""
    if current_user.is_authenticated:
        if current_user.is_organizer:
            return redirect(url_for("organizer_dashboard"))
        return redirect(url_for("home"))

    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            error = "Invalid email or password."
        else:
            login_user(user)

            if user.is_organizer:
                return redirect(url_for("organizer_dashboard"))
            return redirect(url_for("home"))

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    """End the current authenticated session."""
    logout_user()
    return redirect(url_for("home"))


@app.route("/")
def home():
    """Show every raffle that is still open for ticket sales."""
    active_raffles = Raffle.query.filter_by(status="Active").all()
    return render_template("index.html", raffles=active_raffles)


@app.route("/raffles/<int:raffle_id>")
def raffle_details(raffle_id):
    """Show the public details page for a single raffle."""
    raffle = db.get_or_404(Raffle, raffle_id)
    return render_template("raffle_detail.html", raffle=raffle)


@app.route("/raffles/<int:raffle_id>/order", methods=["GET", "POST"])
@participant_required
def create_order(raffle_id):
    """Collect participant details and create a ticket order.

    On POST, validates the submitted data, then creates the
    Participant, TicketOrder, and one Ticket row per ticket purchased.
    Ticket numbers are assigned per-raffle by continuing from the
    highest ticket_number already issued for that raffle, so numbers
    stay sequential and unique even across multiple orders.
    """
    raffle = db.get_or_404(Raffle, raffle_id)

    if request.method == "GET" and raffle.status != "Active":
        return redirect(url_for("raffle_details", raffle_id=raffle.id))

    error = None

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()

        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            quantity = 0

        tickets_remaining = raffle.ticket_limit - len(raffle.tickets)

        if raffle.status != "Active":
            error = "This raffle is not accepting ticket orders."
        elif quantity < 1:
            error = "Select at least one ticket."
        elif quantity > tickets_remaining:
            error = "The requested quantity exceeds the available tickets."
        else:
            participant = Participant(
                name=current_user.name,
                email=current_user.email,
                phone=phone,
            )
            db.session.add(participant)
            db.session.flush()

            order = TicketOrder(
                raffle_id=raffle.id,
                participant_id=participant.id,
                user_id=current_user.id,
                quantity=quantity,
                total_price=round(quantity * raffle.ticket_price, 2),
                payment_status="Pending",
            )
            db.session.add(order)
            db.session.flush()

            # Continue ticket numbering from the highest number already
            # issued for this raffle so identifiers stay unique and
            # sequential across every order placed against it.
            last_ticket_number = (
                db.session.query(db.func.max(Ticket.ticket_number))
                .filter(Ticket.raffle_id == raffle.id)
                .scalar()
                or 0
            )

            for number in range(
                last_ticket_number + 1,
                last_ticket_number + quantity + 1,
            ):
                ticket = Ticket(
                    order_id=order.id,
                    raffle_id=raffle.id,
                    ticket_number=number,
                )
                db.session.add(ticket)

            db.session.commit()

            return redirect(
                url_for("order_confirmation", order_id=order.id)
            )

    return render_template(
        "order.html",
        raffle=raffle,
        error=error,
    )


@app.route("/orders/<int:order_id>/confirmation")
def order_confirmation(order_id):
    """Show the confirmation page listing the tickets just purchased."""
    order = db.get_or_404(TicketOrder, order_id)
    return render_template("confirmation.html", order=order)


@app.route("/organizer")
@organizer_required
def organizer_dashboard():
    """Show every raffle and every order for the organizer to manage."""
    raffles = Raffle.query.order_by(Raffle.created_at.desc()).all()
    orders = TicketOrder.query.order_by(TicketOrder.created_at.desc()).all()

    return render_template(
        "organizer.html",
        raffles=raffles,
        orders=orders,
    )


@app.route(
    "/organizer/orders/<int:order_id>/payment",
    methods=["POST"],
)
@organizer_required
def update_payment_status(order_id):
    """Update an order's simulated payment status.

    Only Pending, Paid, and Cancelled are accepted; any other value in
    the submitted form is silently ignored so the order is left
    unchanged rather than saved in an invalid state.
    """
    order = db.get_or_404(TicketOrder, order_id)
    new_status = request.form.get("payment_status")

    allowed_statuses = {"Pending", "Paid", "Cancelled"}

    if new_status in allowed_statuses:
        order.payment_status = new_status
        db.session.commit()

    return redirect(url_for("organizer_dashboard"))


@app.route("/organizer/raffles/create", methods=["GET", "POST"])
@organizer_required
def create_raffle():
    """Create a new raffle from organizer-submitted form data."""
    error = None

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        prize = request.form.get("prize", "").strip()

        try:
            ticket_price = float(request.form.get("ticket_price", "0"))
            ticket_limit = int(request.form.get("ticket_limit", "0"))
            closing_date = datetime.fromisoformat(
                request.form.get("closing_date", "")
            )
        except ValueError:
            ticket_price = 0
            ticket_limit = 0
            closing_date = None

        if not title or not description or not prize:
            error = "Complete all raffle information."
        elif ticket_price <= 0:
            error = "Ticket price must be greater than zero."
        elif ticket_limit < 1:
            error = "Ticket limit must be at least one."
        elif closing_date is None:
            error = "Enter a valid closing date."
        elif closing_date <= datetime.now():
            error = "Closing date must be in the future."
        else:
            raffle = Raffle(
                title=title,
                description=description,
                prize=prize,
                ticket_price=round(ticket_price, 2),
                ticket_limit=ticket_limit,
                closing_date=closing_date,
                status="Active",
            )

            db.session.add(raffle)
            db.session.commit()

            return redirect(url_for("organizer_dashboard"))

    return render_template("create_raffle.html", error=error)


@app.route(
    "/organizer/raffles/<int:raffle_id>/close",
    methods=["POST"],
)
@organizer_required
def close_raffle(raffle_id):
    """Stop ticket sales for a raffle so it becomes eligible for a draw."""
    raffle = db.get_or_404(Raffle, raffle_id)

    if raffle.status == "Active":
        raffle.status = "Closed"
        db.session.commit()

    return redirect(url_for("organizer_dashboard"))


@app.route(
    "/organizer/raffles/<int:raffle_id>/draw",
    methods=["POST"],
)
@organizer_required
def draw_winner(raffle_id):
    """Randomly select a winning ticket from paid, eligible tickets.

    Only tickets attached to a Paid order are eligible. The raffle
    must already be Closed, and the draw is idempotent: because
    Winner.raffle_id is unique and this route only runs the random
    selection when raffle.winner is still None, submitting the draw
    again for the same raffle has no further effect.
    """
    raffle = db.get_or_404(Raffle, raffle_id)

    eligible_tickets = (
        Ticket.query
        .join(TicketOrder)
        .filter(
            Ticket.raffle_id == raffle.id,
            TicketOrder.payment_status == "Paid",
        )
        .all()
    )

    if (
        raffle.status == "Closed"
        and raffle.winner is None
        and eligible_tickets
    ):
        winning_ticket = random.choice(eligible_tickets)

        winner = Winner(
            raffle_id=raffle.id,
            ticket_id=winning_ticket.id,
        )

        db.session.add(winner)
        db.session.commit()

    return redirect(url_for("organizer_dashboard"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    # debug=True is left on for local course development so template
    # and route changes reload automatically. Turn this off (or read it
    # from an environment variable) before running anywhere reachable
    # outside your own machine, since the debugger can execute code.
    app.run(debug=True)
