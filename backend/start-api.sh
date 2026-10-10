#!/bin/sh
# Apply migrations, then serve. No --proxy-headers: the auth check needs the real peer address.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8820 --workers 2 --no-server-header
