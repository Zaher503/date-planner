"""Registered discovery adapters, by name."""
from app.discover.adapters.ticketmaster import Ticketmaster

ADAPTERS = {a.name: a for a in (Ticketmaster,)}
