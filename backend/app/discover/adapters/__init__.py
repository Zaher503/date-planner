"""Registered discovery adapters, by name."""
from app.discover.adapters.eventbrite_web import EventbriteWeb
from app.discover.adapters.luma import Luma
from app.discover.adapters.resident_advisor import ResidentAdvisor
from app.discover.adapters.ticketmaster import Ticketmaster

ADAPTERS = {a.name: a for a in (Ticketmaster, ResidentAdvisor, Luma, EventbriteWeb)}
