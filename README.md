# DrawBridge

DrawBridge is a full-stack raffle management application built with Python, Flask, Flask-SQLAlchemy, Flask-Login, Jinja templates, and SQLite. It supports participant ticket purchases and an organizer-controlled raffle lifecycle with authentication, role-based authorization, business-rule enforcement, randomized winner selection, audit records, and archived raffles.

## Features

### Participant Features

- Register a participant account
- Log in and log out securely
- Browse active raffles
- View raffle details and ticket availability
- Purchase tickets using the authenticated account
- Receive unique raffle-specific ticket numbers
- View order confirmation and simulated payment status

### Organizer Features

- Log in through a protected organizer account
- Create raffles with validated closing dates and ticket limits
- View raffle orders and participant information
- Update payment status before winner selection
- Close ticket sales
- Select a random winner from paid tickets
- View the recorded winner-selection audit information
- Archive completed raffles

### Business Rules and Integrity

- Organizer routes require an authenticated organizer account
- Ticket purchases require an authenticated participant account
- Passwords are stored as secure hashes
- Ticket purchases cannot exceed the remaining ticket supply
- Expired raffles close automatically
- Winners can only be selected from paid tickets
- A raffle can have only one winner
- Winner selection records the eligible-ticket count, selection method, selecting organizer, and timestamp
- Payment eligibility cannot change after winner selection
- Archived raffles retain their winner and audit information

## Technology

- Python
- Flask
- Flask-Login
- Flask-SQLAlchemy
- SQLAlchemy
- SQLite
- Jinja
- HTML and CSS
- pytest
- Git and GitHub

## Installation

Clone the repository and enter the project directory:

```powershell
git clone https://github.com/pedgecombe/DrawBridge.git
cd DrawBridge
git switch assignment-3
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

Install the required packages:

```powershell
python -m pip install -r requirements.txt
```

## Database Setup

Set a password for the organizer account in the current PowerShell session:

```powershell
$env:DRAWBRIDGE_ORGANIZER_PASSWORD = "Choose-A-Secure-Demo-Password"
```

Optionally set a separate Flask session key:

```powershell
$env:DRAWBRIDGE_SECRET_KEY = "Choose-A-Random-Secret-Key"
```

Create the database, organizer account, and sample raffle:

```powershell
python seed.py
```

The organizer email address is:

```text
organizer@drawbridge.local
```

The organizer password is the value assigned to `DRAWBRIDGE_ORGANIZER_PASSWORD`. The password is not stored in the source code or committed to Git.

The seed script can be run again safely. It only creates the organizer and sample raffle when they do not already exist.

## Running the Application

Start DrawBridge:

```powershell
python app.py
```

Open the application at:

```text
http://127.0.0.1:5000
```

Participant accounts can be created from the registration page. Organizer access uses the seeded organizer account.

## Running the Automated Tests

Run the complete test suite:

```powershell
python -m pytest -q
```

The automated tests use a separate in-memory SQLite database. Running pytest does not modify the application database in the `instance` directory.

The suite covers:

- Password hashing and user roles
- Registration, login, and logout
- Organizer and participant authorization
- Participant ownership of ticket orders
- Ticket-number generation
- Ticket availability and purchase boundaries
- Raffle creation validation
- Automatic closing-date enforcement
- Payment-status validation and restrictions
- Winner eligibility
- Randomized and idempotent winner selection
- Winner-selection audit records
- Raffle archiving
- Restrictions after winner selection

## Raffle Lifecycle

A raffle follows this controlled lifecycle:

```text
Active -> Closed -> Completed -> Archived
```

- `Active`: participants can purchase tickets and the organizer can manage payment status.
- `Closed`: ticket sales have ended and the organizer can select a winner.
- `Completed`: a winner has been selected and the result is locked.
- `Archived`: the completed raffle and audit information are retained for historical reference.

## Project Structure

```text
DrawBridge/
|-- app.py
|-- models.py
|-- seed.py
|-- requirements.txt
|-- README.md
|-- static/
|   `-- style.css
|-- templates/
|   |-- base.html
|   |-- confirmation.html
|   |-- create_raffle.html
|   |-- index.html
|   |-- login.html
|   |-- order.html
|   |-- organizer.html
|   |-- raffle_detail.html
|   `-- register.html
`-- tests/
    `-- test_app.py
```

## Scope and Limitations

DrawBridge is an academic prototype. Payment status is simulated, and the application does not connect to a payment processor or send email notifications. SQLite is appropriate for the project scope but would require additional deployment planning for heavier concurrent use. The built-in Flask development server is intended for local demonstration and testing.