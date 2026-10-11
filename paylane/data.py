"""Seeded fake Paylane data. TODAY is fixed so age-based rules are deterministic."""
from datetime import date
import copy

TODAY = date(2026, 10, 11)

_CUSTOMERS = {
    "C001": {"id": "C001", "name": "Aisha Khan", "email": "aisha@example.com", "card_last4": "4242", "status": "active", "freeze_reason": None},
    "C002": {"id": "C002", "name": "Ben Ortiz", "email": "ben@example.com", "card_last4": "1881", "status": "frozen", "freeze_reason": "Unusual login from a new country"},
    "C003": {"id": "C003", "name": "Chen Wei", "email": "chen@example.com", "card_last4": "0007", "status": "active", "freeze_reason": None},
}

# txn_id -> record (customer_id included for ownership checks)
_TRANSACTIONS = {
    "T100": {"customer_id": "C001", "amount": 42.50,  "date": "2026-10-01", "merchant": "Spotify",      "status": "settled"},   # plain auto-refund
    "T101": {"customer_id": "C001", "amount": 75.00,  "date": "2026-10-05", "merchant": "Uber",         "status": "settled"},   # exactly $75 boundary
    "T102": {"customer_id": "C001", "amount": 120.00, "date": "2026-10-03", "merchant": "Zara",         "status": "settled"},   # > $75 -> escalate
    "T103": {"customer_id": "C001", "amount": 30.00,  "date": "2026-08-20", "merchant": "Netflix",      "status": "settled"},   # > 30 days -> escalate (52 days)
    "T104": {"customer_id": "C001", "amount": 20.00,  "date": "2026-09-11", "merchant": "Starbucks",    "status": "settled"},   # exactly 30 days old (age=30, excluded)
    "T105": {"customer_id": "C001", "amount": 15.00,  "date": "2026-10-10", "merchant": "Amazon",       "status": "pending"},   # pending (now refundable per policy)
    "T106": {"customer_id": "C001", "amount": 25.00,  "date": "2026-10-02", "merchant": "Apple",        "status": "settled"},   # for partial refund testing
    "T107": {"customer_id": "C001", "amount": 10.00,  "date": "2026-10-01", "merchant": "Coffee Shop",  "status": "settled"},   # for cumulative testing
    "T200": {"customer_id": "C002", "amount": 60.00,  "date": "2026-10-04", "merchant": "Steam",        "status": "settled"},   # frozen-card customer
    "T300": {"customer_id": "C003", "amount": 900.00, "date": "2026-10-06", "merchant": "CryptoXchange","status": "settled"},   # large fraud claim
    "T301": {"customer_id": "C003", "amount": 50.00,  "date": "2026-10-07", "merchant": "Lyft",         "status": "settled"},   # small fraud claim
}


class Store:
    """Fresh mutable copy per conversation, plus an audit log of tool calls."""
    def __init__(self):
        self.customers = copy.deepcopy(_CUSTOMERS)
        self.transactions = copy.deepcopy(_TRANSACTIONS)
        self.refunds = {}   # refund_id -> {txn_id, amount}
        self.tickets = {}   # ticket_id -> {customer_id, summary}
        self.calls = []     # [(tool_name, args, result)]
