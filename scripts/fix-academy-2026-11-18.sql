-- One-off data fix of the live database, 2026-11-18. Data edits only: no schema change.
--
-- 1. "Drop-in Workshop for Teens: Editing for Horror Films" is one date (Fri Nov 20, 2026, per the museum's
--    program page), not "third Friday of every month" (that is the whole teen-workshop series, a new topic
--    each month). Make it an all-day one-off with its date row.
-- 2. "Oscars" said "ongoing until 2027-01-10" (the Bong Joon Ho exhibition's first closing date). The museum
--    lists it as Ongoing.
-- Both are marked as hand edits so a later read of the page does not overwrite them.
--
-- Run: ssh zephyrus 'cd /opt/date-planner/deploy && docker compose exec -T db psql -U dates dates -v ON_ERROR_STOP=1' < scripts/fix-academy-2026-11-18.sql
-- Undo: set recurrence_text back to 'third Friday of every month' / 'ongoing until 2027-01-10', clear the
--       workshop's starts_at/ends_at, delete its occurrence and drop the added user_overrides keys.

begin;

update events set starts_at = '2026-11-20 00:00 America/Los_Angeles', ends_at = '2026-11-21 00:00 America/Los_Angeles',
  all_day = true, duration_min = null, recurrence_text = null, rrule = null,
  user_overrides = user_overrides || '{"starts_at": true, "ends_at": true, "recurrence_text": true, "rrule": true}'::jsonb,
  updated_at = now()
where id = '318001b1-86c5-4a06-9bcd-5a0ba2180c59';

insert into occurrences (event_id, starts_at, ends_at)
values ('318001b1-86c5-4a06-9bcd-5a0ba2180c59', '2026-11-20 00:00 America/Los_Angeles',
        '2026-11-21 00:00 America/Los_Angeles')
on conflict on constraint uq_occurrence do nothing;

update events set recurrence_text = 'ongoing',
  user_overrides = user_overrides || '{"recurrence_text": true}'::jsonb, updated_at = now()
where id = '05744f36-4514-4663-b66d-cde9e9192290';

select title, starts_at, ends_at, all_day, recurrence_text, user_overrides from events
where id in ('318001b1-86c5-4a06-9bcd-5a0ba2180c59', '05744f36-4514-4663-b66d-cde9e9192290');

commit;
