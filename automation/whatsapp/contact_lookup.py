"""
Multi-Strategy Contact Lookup Engine
=====================================

Searches contacts in SQLite database and in-memory phonebook.
Supports:
  - Exact match (case-insensitive)
  - Nickname match
  - Partial match
  - Multiple matches
  - No match
"""

from __future__ import annotations
import os
import sqlite3
import logging
from typing import List, Optional
from storage.database import DB_PATH
from automation.whatsapp.schemas import ContactItem, ContactLookupResult
from automation.whatsapp.constants import (
    LOOKUP_STATUS_EXACT,
    LOOKUP_STATUS_NICKNAME,
    LOOKUP_STATUS_PARTIAL,
    LOOKUP_STATUS_MULTIPLE,
    LOOKUP_STATUS_NOT_FOUND,
)

logger = logging.getLogger("automation.whatsapp.contact_lookup")

# Built-in phonebook default contacts
DEFAULT_PHONEBOOK: List[ContactItem] = [
    ContactItem(name="Harshita", phone_number="+919876543210", nickname="Harshu", email="harshita@example.com"),
    ContactItem(name="Rahul", phone_number="+919876543211", nickname="Rahul V", email="rahul@example.com"),
    ContactItem(name="Mom", phone_number="+919876543212", nickname="Mother", email="mom@example.com"),
    ContactItem(name="Dad", phone_number="+919876543213", nickname="Father", email="dad@example.com"),
    ContactItem(name="Boss", phone_number="+919876543214", nickname="Manager", email="boss@example.com"),
    ContactItem(name="Alex", phone_number="+919876543215", nickname="Al", email="alex@example.com"),
]

_TABLE_INIT_DONE = False


def _init_contacts_table() -> None:
    """Ensure contacts table exists in SQLite database."""
    global _TABLE_INIT_DONE
    if _TABLE_INIT_DONE:
        return
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                nickname     TEXT,
                email        TEXT
            )
        """)
        conn.commit()

        # Populate defaults if empty
        cursor = conn.execute("SELECT COUNT(*) FROM contacts")
        count = cursor.fetchone()[0]
        if count == 0:
            for c in DEFAULT_PHONEBOOK:
                conn.execute(
                    "INSERT INTO contacts (name, phone_number, nickname, email) VALUES (?, ?, ?, ?)",
                    (c.name, c.phone_number, c.nickname, c.email),
                )
            conn.commit()
            logger.info("[CONTACT LOOKUP] Initialized contacts table with default phonebook entries.")
        conn.close()
        _TABLE_INIT_DONE = True
    except Exception as e:
        logger.warning("[CONTACT LOOKUP] Failed to init contacts SQLite table: %s", e)


class ContactLookupService:
    """Engine for finding contacts across SQLite DB and in-memory phonebook."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        _init_contacts_table()

    def _get_all_contacts(self) -> List[ContactItem]:
        """Fetch all contacts from SQLite DB or fall back to default phonebook."""
        contacts: List[ContactItem] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM contacts").fetchall()
            conn.close()

            for r in rows:
                contacts.append(
                    ContactItem(
                        id=r["id"],
                        name=r["name"],
                        phone_number=r["phone_number"],
                        nickname=r["nickname"],
                        email=r["email"],
                    )
                )
        except Exception as e:
            logger.warning("[CONTACT LOOKUP] Failed to query SQLite DB: %s. Using default phonebook.", e)
            contacts = DEFAULT_PHONEBOOK.copy()

        if not contacts:
            contacts = DEFAULT_PHONEBOOK.copy()
        return contacts

    def search(self, query: str) -> ContactLookupResult:
        """Search contacts by query string.

        Supports:
          1. Exact match (case-insensitive)
          2. Nickname match (case-insensitive)
          3. Partial match (name/nickname contains query)
        """
        if not query or not query.strip():
            return ContactLookupResult(status=LOOKUP_STATUS_NOT_FOUND, query=query or "")

        clean_q = query.strip().lower()
        all_contacts = self._get_all_contacts()

        # Strategy 1: Exact name match
        exact_matches = [c for c in all_contacts if c.name.strip().lower() == clean_q]
        if len(exact_matches) == 1:
            logger.info("[CONTACT LOOKUP] Exact match found: %s (%s)", exact_matches[0].name, exact_matches[0].phone_number)
            return ContactLookupResult(
                status=LOOKUP_STATUS_EXACT,
                query=query,
                selected_contact=exact_matches[0],
            )
        elif len(exact_matches) > 1:
            logger.info("[CONTACT LOOKUP] Multiple exact matches found (%d) for '%s'", len(exact_matches), query)
            return ContactLookupResult(
                status=LOOKUP_STATUS_MULTIPLE,
                query=query,
                candidates=exact_matches,
            )

        # Strategy 2: Nickname match
        nickname_matches = [
            c for c in all_contacts if c.nickname and c.nickname.strip().lower() == clean_q
        ]
        if len(nickname_matches) == 1:
            logger.info("[CONTACT LOOKUP] Nickname match found: %s (%s)", nickname_matches[0].name, nickname_matches[0].phone_number)
            return ContactLookupResult(
                status=LOOKUP_STATUS_NICKNAME,
                query=query,
                selected_contact=nickname_matches[0],
            )
        elif len(nickname_matches) > 1:
            logger.info("[CONTACT LOOKUP] Multiple nickname matches found (%d) for '%s'", len(nickname_matches), query)
            return ContactLookupResult(
                status=LOOKUP_STATUS_MULTIPLE,
                query=query,
                candidates=nickname_matches,
            )

        # Strategy 3: Partial match
        partial_matches = [
            c for c in all_contacts
            if clean_q in c.name.lower() or (c.nickname and clean_q in c.nickname.lower())
        ]

        if len(partial_matches) == 1:
            logger.info("[CONTACT LOOKUP] Partial match found: %s (%s)", partial_matches[0].name, partial_matches[0].phone_number)
            return ContactLookupResult(
                status=LOOKUP_STATUS_PARTIAL,
                query=query,
                selected_contact=partial_matches[0],
            )
        elif len(partial_matches) > 1:
            logger.info("[CONTACT LOOKUP] Multiple partial matches found (%d) for '%s'", len(partial_matches), query)
            return ContactLookupResult(
                status=LOOKUP_STATUS_MULTIPLE,
                query=query,
                candidates=partial_matches,
            )

        # Strategy 4: Direct phone number input check
        if clean_q.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            clean_digits = clean_q.replace("+", "").replace("-", "").replace(" ", "")
            direct_contact = ContactItem(name=query, phone_number=f"+{clean_digits}")
            return ContactLookupResult(status=LOOKUP_STATUS_EXACT, query=query, selected_contact=direct_contact)

        logger.info("[CONTACT LOOKUP] No contacts found matching query '%s'", query)
        return ContactLookupResult(status=LOOKUP_STATUS_NOT_FOUND, query=query)
