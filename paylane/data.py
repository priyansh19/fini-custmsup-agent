"""Seeded fake Paylane data. TODAY is fixed so age-based rules are deterministic."""
from datetime import date
import copy

TODAY = date(2026, 10, 11)

_CUSTOMERS = {
    "PL-48213": {"id": "PL-48213", "name": "Amara Okafor", "email": "amara.okafor@maplecrest.test", "card_last4": "6417", "status": "active", "freeze_reason": None},
    "PL-51907": {"id": "PL-51907", "name": "Mateo Alvarez", "email": "mateo.alvarez@maplecrest.test", "card_last4": "3058", "status": "frozen", "freeze_reason": "Unusual login from a new country"},
    "PL-36642": {"id": "PL-36642", "name": "Mei-Lin Tan", "email": "meilin.tan@maplecrest.test", "card_last4": "9126", "status": "active", "freeze_reason": None},
}

# txn_id -> record (customer_id included for ownership checks)
_TRANSACTIONS = {
    "TXN-58214": {"customer_id": "PL-48213", "amount": 42.50,  "date": "2026-10-01", "merchant": "Spotify",      "status": "settled"},   # plain auto-refund
    "TXN-58237": {"customer_id": "PL-48213", "amount": 75.00,  "date": "2026-10-05", "merchant": "Uber",         "status": "settled"},   # exactly $75 boundary
    "TXN-58241": {"customer_id": "PL-48213", "amount": 120.00, "date": "2026-10-03", "merchant": "Zara",         "status": "settled"},   # > $75 -> escalate
    "TXN-57106": {"customer_id": "PL-48213", "amount": 30.00,  "date": "2026-08-20", "merchant": "Netflix",      "status": "settled"},   # > 30 days -> escalate (52 days)
    "TXN-57552": {"customer_id": "PL-48213", "amount": 20.00,  "date": "2026-09-11", "merchant": "Starbucks",    "status": "settled"},   # exactly 30 days old (age=30, excluded)
    "TXN-58306": {"customer_id": "PL-48213", "amount": 15.00,  "date": "2026-10-10", "merchant": "Amazon",       "status": "pending"},   # pending (now refundable per policy)
    "TXN-58219": {"customer_id": "PL-48213", "amount": 25.00,  "date": "2026-10-02", "merchant": "Apple",        "status": "settled"},   # for partial refund testing
    "TXN-58209": {"customer_id": "PL-48213", "amount": 10.00,  "date": "2026-10-01", "merchant": "Blue Bottle Coffee",  "status": "settled"},   # for cumulative testing
    "TXN-58244": {"customer_id": "PL-48213", "amount": 40.00,  "date": "2026-10-03", "merchant": "DoorDash",     "status": "settled"},   # for cumulative limit testing
    "TXN-58262": {"customer_id": "PL-48213", "amount": 75.01,  "date": "2026-10-05", "merchant": "BestBuy",      "status": "settled"},   # $75.01 -> over hard cap
    "TXN-57560": {"customer_id": "PL-48213", "amount": 20.00,  "date": "2026-09-12", "merchant": "Equinox",          "status": "settled"},   # age 29 -> refundable
    "TXN-57549": {"customer_id": "PL-48213", "amount": 20.00,  "date": "2026-09-10", "merchant": "Waterstones",    "status": "settled"},   # age 31 -> too old
    "TXN-58277": {"customer_id": "PL-48213", "amount": 32.50,  "date": "2026-10-06", "merchant": "Uniqlo",       "status": "settled"},   # TXN-58214+TXN-58237+TXN-58277 = exactly $150
    "TXN-61450": {"customer_id": "PL-51907", "amount": 60.00,  "date": "2026-10-04", "merchant": "Steam",        "status": "settled"},   # frozen-card customer
    "TXN-73318": {"customer_id": "PL-36642", "amount": 900.00, "date": "2026-10-06", "merchant": "CoinVault Exchange","status": "settled"},   # large fraud claim
    "TXN-73325": {"customer_id": "PL-36642", "amount": 50.00,  "date": "2026-10-07", "merchant": "Lyft",         "status": "settled"},   # small fraud claim
}


class Store:
    """Fresh mutable copy per conversation, plus an audit log of tool calls."""
    def __init__(self):
        self.customers = copy.deepcopy(_CUSTOMERS)
        self.transactions = copy.deepcopy(_TRANSACTIONS)
        self.refunds = {}   # refund_id -> {txn_id, amount}
        self.tickets = {}   # ticket_id -> {customer_id, summary}
        self.calls = []     # [(tool_name, args, result)]
