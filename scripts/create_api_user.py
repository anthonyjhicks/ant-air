#!/usr/bin/env python3
"""Create an API user for iOS app authentication.

Usage:
    python scripts/create_api_user.py <username>
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import ApiUser

if len(sys.argv) < 2:
    print("Usage: python scripts/create_api_user.py <username>")
    sys.exit(1)

username = sys.argv[1]

app = create_app()
with app.app_context():
    existing = ApiUser.query.filter_by(username=username).first()
    if existing:
        print(f"Error: user '{username}' already exists.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match.")
        sys.exit(1)

    user = ApiUser(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"API user '{username}' created successfully.")
