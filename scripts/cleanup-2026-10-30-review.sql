-- Clears the items still marked "needs review" after cleanup-2026-10-30.sql, each checked against its source.
-- Same usage: dry run by default, add -v commit=1 to keep the changes. Take a pg_dump first.

\set ON_ERROR_STOP on
BEGIN;

\echo == before
SELECT (SELECT count(*) FROM places WHERE review_status = 'needs_review') AS places_to_review,
       (SELECT count(*) FROM events WHERE review_status = 'needs_review') AS events_to_review,
       (SELECT count(*) FROM places) AS places, (SELECT count(*) FROM events) AS events;

-- The Magic Castle: address confirmed on magiccastle.com; a private club
UPDATE places SET review_status = 'ok', phone = '(323) 851-3313',
    hours_text = 'Dinner daily 5 pm to 1 am, brunch Saturday and Sunday 9 am to 4 pm. Private club: invited guests and members only.'
    WHERE name = 'The Magic Castle';

-- Sender One Thousand Oaks is not open until 2027, and the LAX yoga class has no schedule or price on the site
DELETE FROM places WHERE name = 'Sender One Thousand Oaks';
DELETE FROM events WHERE id::text LIKE 'ce6ef35a%' AND title = 'yoga class';

-- Academy Museum exhibitions: dates from academymuseum.org/en/exhibitions. The rows stop being a
-- "recurring series", so they move to the Archive by themselves after the closing date.
CREATE TEMP TABLE exhibit (id_prefix text, opens date, closes date);
INSERT INTO exhibit VALUES
    ('f308975e', '2026-09-26', '2027-07-25'),  -- The Horror Show
    ('b7b9cbc6', '2025-03-23', '2027-10-24'),  -- Director's Inspiration: Bong Joon Ho
    ('397d81b4', '2026-08-29', '2027-07-18'),  -- Glow: A Cinematic Moodscape
    ('0d46ac6f', '2026-05-31', '2027-02-28'),  -- Marilyn Monroe: Hollywood Icon
    ('5cff1d58', '2026-02-14', '2027-03-21');  -- Studio Ghibli's PONYO
UPDATE events e SET
        starts_at = (x.opens::text || ' 00:00 America/Los_Angeles')::timestamptz,
        ends_at = (x.closes::text || ' 23:59 America/Los_Angeles')::timestamptz,
        all_day = true, recurrence_text = NULL, review_status = 'ok'
    FROM exhibit x WHERE e.id::text LIKE x.id_prefix || '%';
INSERT INTO occurrences (event_id, starts_at, ends_at)
    SELECT e.id, e.starts_at, e.ends_at FROM events e JOIN exhibit x ON e.id::text LIKE x.id_prefix || '%'
    ON CONFLICT DO NOTHING;
-- Oscars: the museum lists it only as "Ongoing", so it keeps its text
UPDATE events SET review_status = 'ok' WHERE id::text LIKE '05744f36%';
-- Barbie to Anna Karenina closed on Oct 18 and is no longer on the museum's page
UPDATE events SET status = 'archived', ends_at = timestamptz '2026-10-18 23:59 America/Los_Angeles',
        all_day = true, recurrence_text = NULL, review_status = 'ok'
    WHERE id::text LIKE '44d55f5a%';

-- Tutu Fun: bookable workshops. Hours, phone, prices and booking link are from tutufuncc.com.
UPDATE places SET phone = '(424) 204-9094',
        hours_text = 'Mon-Thu 10 am to 9 pm, Fri-Sat 10 am to 10 pm, Sun 10 am to 8 pm',
        opening_hours = 'Mo-Th 10:00-21:00; Fr-Sa 10:00-22:00; Su 10:00-20:00'
    WHERE name = 'Tutu Fun';
CREATE TEMP TABLE workshop (title text, lo numeric, hi numeric, price_text text);
INSERT INTO workshop VALUES
    ('Rug Tufting', 68, 168, 'Mini $68, Small $78, Large $168'),
    ('Pouring Arts', 20, 108, 'Fluid Bear $20-108, Fluid Bunny $58, Fluid Painting $28-48'),
    ('Decoden Arts', 20, 50, 'Hair Clamp $20 up to Water Bottle $50'),
    ('Beading Arts', 16, 54, 'Bead Pen $16-22 up to Bead Bag Chain $46-54'),
    ('Candle Making', 38, 76, 'Cup Candle $38-76, Cake Candle $54-64'),
    ('Sensory Art', 35, 52, 'Squishy Ball $35, Regular $46, Premium $52');
-- The text must not read as a repeat pattern (the recurrence parser would turn "daily" into a daily series)
UPDATE events e SET price_min = w.lo, price_max = w.hi, price_text = w.price_text, is_free = false,
        recurrence_text = 'Book online for a time slot', ticket_url = 'https://tutufuncc.com/reservation/',
        review_status = 'ok'
    FROM workshop w WHERE e.title = w.title AND e.place_id = (SELECT id FROM places WHERE name = 'Tutu Fun');

-- The Empire Strips Back: dates confirmed (Oct 1-11, 2026), the run is over
UPDATE events SET review_status = 'ok' WHERE title = 'The Empire Strips Back';

\echo == after
SELECT (SELECT count(*) FROM places WHERE review_status = 'needs_review') AS places_to_review,
       (SELECT count(*) FROM events WHERE review_status = 'needs_review') AS events_to_review,
       (SELECT count(*) FROM places) AS places, (SELECT count(*) FROM events) AS events;
\echo == exhibitions
SELECT title, starts_at::date AS opens, ends_at::date AS closes, status FROM events
    WHERE place_id = (SELECT id FROM places WHERE name = 'Academy Museum of Motion Pictures') ORDER BY title;

\if :{?commit}
    \echo == COMMITTING
    COMMIT;
\else
    \echo == DRY RUN, rolling back. Run again with -v commit=1 to keep the changes
    ROLLBACK;
\endif
