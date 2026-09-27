# DrawBridge

DrawBridge is a prototype raffle-management application developed in Python using Flask, Flask-SQLAlchemy, and SQLite.

## Current Features

- Display active raffles
- View raffle details and ticket availability
- Record participant information
- Submit ticket orders
- Generate raffle-specific ticket identifiers
- Track simulated payment status
- Create and close raffles
- Randomly select a winner from paid tickets
- Prevent repeated winner selection
- Display organizer and winner information

## Installation

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

## Running the Application

Start DrawBridge once to create the database:

```powershell
python app.py
```

Stop the server with `Ctrl+C`, then create the sample raffle:

```powershell
python seed.py
```

Restart DrawBridge:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Organizer Dashboard

The organizer dashboard is available at:

```text
http://127.0.0.1:5000/organizer
```

## Running the Tests

An automated test suite exercises ticket numbering, ticket-availability
validation, payment status updates, and the winner draw (including
that a raffle can only ever have one winner). Run it with:

```powershell
python -m pytest
```

## Prototype Limitations

This version uses simulated payment records and does not process real financial transactions. Organizer authentication, expanded testing, automatic closing-date enforcement, and a more detailed draw audit record can be added during later development.