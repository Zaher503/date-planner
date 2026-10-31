-- One-off data cleanup of the live database, 2026-10-30.
--
-- Merges places that are parts of a bigger venue into events on that venue, deletes ghost places
-- and junk events, and fixes wrong addresses and websites. Data edits only: no schema change.
--
-- Run it dry first (rolls back at the end and prints what it would do), then for real:
--   docker compose exec -T db psql -U dates dates < cleanup-2026-10-30.sql
--   docker compose exec -T db psql -U dates dates -v commit=1 < cleanup-2026-10-30.sql
-- Take a pg_dump first. It stops at the first error and the whole script is one transaction.

\set ON_ERROR_STOP on
BEGIN;

-- Refuse to run if the data is not what the plan was written against
DO $$
BEGIN
    IF (SELECT count(*) FROM places) <> 56 OR (SELECT count(*) FROM events) <> 30 THEN
        RAISE EXCEPTION 'expected 56 places and 30 events, the data has changed since the plan';
    END IF;
    IF (SELECT count(*) FROM events WHERE id::text ~ '^(c19a2d6c|28b73810|68ea0c35|1c51dcec|df832bc2|81fbc52e|399bf991|345ab17b|bbae2c1b)'
        AND title IN ('Climbing', 'Bouldering', 'Sender City', 'yoga')) <> 9 THEN
        RAISE EXCEPTION 'the 9 Sender One events to delete are not all there';
    END IF;
END $$;

\echo == before
SELECT (SELECT count(*) FROM places) AS places, (SELECT count(*) FROM events) AS events,
       (SELECT count(*) FROM item_sources) AS item_sources;

-- Helpers (live for this session only)
CREATE FUNCTION pg_temp.pid(n text) RETURNS uuid LANGUAGE sql AS $$ SELECT id FROM places WHERE name = n $$;
CREATE FUNCTION pg_temp.eid(t text, p uuid) RETURNS uuid LANGUAGE sql AS
    $$ SELECT id FROM events WHERE title = t AND place_id = p $$;
CREATE FUNCTION pg_temp.pt(lon float8, lat float8) RETURNS geography LANGUAGE sql AS
    $$ SELECT ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography $$;

-- Keep where an item came from and its pictures when its place row is about to be deleted
CREATE FUNCTION pg_temp.move_to_place(old uuid, new uuid) RETURNS void LANGUAGE sql AS $$
    INSERT INTO item_sources (source_id, place_id, position, confidence, mention_at)
        SELECT source_id, new, position, confidence, mention_at FROM item_sources WHERE place_id = old
        ON CONFLICT DO NOTHING;
    UPDATE item_images SET place_id = new WHERE place_id = old;
$$;
CREATE FUNCTION pg_temp.move_to_event(old uuid, new uuid) RETURNS void LANGUAGE sql AS $$
    INSERT INTO item_sources (source_id, event_id, position, confidence, mention_at)
        SELECT source_id, new, position, confidence, mention_at FROM item_sources WHERE place_id = old
        ON CONFLICT DO NOTHING;
    UPDATE item_images SET place_id = NULL, event_id = new WHERE place_id = old;
$$;

-- 1. Hollywood Roosevelt: Cinegrill Theater, Library Bar and The Spare Room are rooms inside it.
-- (The Spare Room place had the phone +1-323-769-9296; it is dropped with the place.)
INSERT INTO places (name, category, geom, address, address_text, description, origin, review_status)
    SELECT 'The Hollywood Roosevelt', 'nightlife', geom, address, address_text,
           'Hotel on Hollywood Boulevard. The Cinegrill Theater, Library Bar and The Spare Room are inside it.',
           'manual', 'ok'
    FROM places WHERE name = 'Cinegrill Theater';

SELECT pg_temp.move_to_place(pg_temp.pid(n), pg_temp.pid('The Hollywood Roosevelt'))
    FROM unnest(ARRAY['Cinegrill Theater', 'Library Bar', 'The Spare Room']) AS n;
-- The events keep the room as venue_name
UPDATE events SET place_id = pg_temp.pid('The Hollywood Roosevelt')
    WHERE place_id IN (pg_temp.pid('Cinegrill Theater'), pg_temp.pid('Library Bar'), pg_temp.pid('The Spare Room'));
DELETE FROM places WHERE name IN ('Cinegrill Theater', 'Library Bar', 'The Spare Room');

-- 2. Academy Museum: Marilyn Monroe and The Horror Show are exhibits
UPDATE events e SET place_id = a.id, geom = a.geom, venue_name = a.name, address_text = a.address_text
    FROM places a
    WHERE a.name = 'Academy Museum of Motion Pictures' AND e.title = 'Marilyn Monroe: Hollywood Icon'
      AND e.place_id = pg_temp.pid('Marilyn Monroe: Hollywood Icon');
SELECT pg_temp.move_to_event(pg_temp.pid('Marilyn Monroe: Hollywood Icon'),
                             pg_temp.eid('Marilyn Monroe: Hollywood Icon', pg_temp.pid('Academy Museum of Motion Pictures')));
DELETE FROM places WHERE name = 'Marilyn Monroe: Hollywood Icon';

INSERT INTO events (place_id, geom, venue_name, address_text, title, description, category, tags, all_day,
                    origin, review_status, import_info)
    SELECT a.id, a.geom, a.name, a.address_text, h.name, h.description, 'museum', h.tags, true,
           'manual', 'needs_review', h.import_info
    FROM places h, places a
    WHERE h.name = 'The Horror Show' AND a.name = 'Academy Museum of Motion Pictures';
SELECT pg_temp.move_to_event(pg_temp.pid('The Horror Show'),
                             pg_temp.eid('The Horror Show', pg_temp.pid('Academy Museum of Motion Pictures')));
DELETE FROM places WHERE name = 'The Horror Show';

-- 3. Tutu Fun: its workshops were also saved as places, with wrong websites and cities
UPDATE places SET address_text = '10250 Santa Monica Boulevard, Los Angeles, California 90067' WHERE name = 'Tutu Fun';

CREATE TEMP TABLE tutu (place_name text, event_title text);
INSERT INTO tutu VALUES ('Pouring Arts', 'Pouring Arts'), ('Decoden Arts', 'Decoden Arts'),
    ('Beading Arts', 'Beading Arts'), ('Sensory Art', 'Sensory Art'), ('Rug Tufting', 'Rug Tufting'),
    ('Cup Candle Making', 'Candle Making');

-- Fill the event from the place where the event has nothing
UPDATE events e SET description = COALESCE(NULLIF(e.description, ''), p.description),
                    tags = COALESCE((SELECT array_agg(DISTINCT t) FROM unnest(e.tags || p.tags) AS t), '{}')
    FROM tutu JOIN places p ON p.name = tutu.place_name
    WHERE e.title = tutu.event_title AND e.place_id = pg_temp.pid('Tutu Fun');
SELECT pg_temp.move_to_event(p.id, e.id)
    FROM tutu JOIN places p ON p.name = tutu.place_name
    JOIN events e ON e.title = tutu.event_title AND e.place_id = pg_temp.pid('Tutu Fun');
DELETE FROM places WHERE name IN (SELECT place_name FROM tutu);
UPDATE events SET address_text = '10250 Santa Monica Boulevard, Los Angeles, California 90067'
    WHERE place_id = pg_temp.pid('Tutu Fun');

-- 4. Sender One: Sender City is a part of the LAX gym; generic events and wrong websites go
UPDATE places l SET description = COALESCE(l.description, c.description),
                    price_text = COALESCE(l.price_text, c.price_text),
                    tags = COALESCE((SELECT array_agg(DISTINCT t) FROM unnest(l.tags || c.tags) AS t), '{}')
    FROM places c WHERE l.name = 'Sender One LAX' AND c.name = 'Sender City';
SELECT pg_temp.move_to_place(pg_temp.pid('Sender City'), pg_temp.pid('Sender One LAX'));
DELETE FROM places WHERE name = 'Sender City';

DELETE FROM events WHERE id::text ~ '^(c19a2d6c|28b73810|68ea0c35|1c51dcec|df832bc2|81fbc52e|399bf991|345ab17b|bbae2c1b)';
UPDATE events SET is_free = NULL WHERE id::text LIKE 'ce6ef35a%';  -- LAX yoga class: no price on the site

UPDATE places SET website = NULL, phone = NULL
    WHERE name IN ('Sender One Aliso Viejo', 'Sender One Westwood', 'Sender One Santa Ana');  -- Lakewood and LAX values
UPDATE places SET website = 'https://www.senderoneclimbing.com/'
    WHERE name IN ('Sender One Aliso Viejo', 'Sender One Westwood', 'Sender One Santa Ana',
                   'Sender One Playa Vista', 'Sender One Thousand Oaks');
UPDATE places SET category = 'activity' WHERE name = 'Sender One Playa Vista';
UPDATE places SET description = 'Opening in 2027 (per senderoneclimbing.com). ' || COALESCE(description, ''),
                   review_status = 'needs_review'
    WHERE name = 'Sender One Thousand Oaks';

-- 5. Creep LA x Ghosts: a show whose 2026 season is cancelled, with no venue address
DELETE FROM places WHERE name = 'Creep LA x Ghosts';

-- 6. The Empire Strips Back: a show at the Montalban Theatre, Oct 1-11 2026
INSERT INTO places (name, category, geom, address_text, description, origin, review_status)
    VALUES ('Montalbán Theatre', 'arts', pg_temp.pt(-118.3267154, 34.101602),
            '1615 Vine Street, Los Angeles, California 90028', 'Theatre at 1615 Vine Street, Hollywood.',
            'manual', 'ok');
INSERT INTO events (place_id, geom, venue_name, address_text, title, description, category, tags, all_day,
                    starts_at, ends_at, ticket_url, origin, review_status, import_info)
    SELECT m.id, m.geom, m.name, m.address_text, e.name, e.description, 'nightlife', e.tags, true,
           timestamptz '2026-10-01 00:00 America/Los_Angeles', timestamptz '2026-10-11 23:59 America/Los_Angeles',
           'https://theempirestripsback.com/los-angeles/', 'manual', 'needs_review', e.import_info
    FROM places e, places m WHERE e.name = 'The Empire Strips Back' AND m.name = 'Montalbán Theatre';
INSERT INTO occurrences (event_id, starts_at, ends_at)
    SELECT id, starts_at, ends_at FROM events WHERE title = 'The Empire Strips Back';
SELECT pg_temp.move_to_event(pg_temp.pid('The Empire Strips Back'),
                             pg_temp.eid('The Empire Strips Back', pg_temp.pid('Montalbán Theatre')));
DELETE FROM places WHERE name = 'The Empire Strips Back';

-- 7. Places with a wrong address or website (coordinates from the local Photon). The old OSM ids pointed
-- at the wrong objects, so they are cleared.
UPDATE places SET address_text = '2100 Zeno Place, Venice, California 90291', geom = pg_temp.pt(-118.4587893, 33.9892209),
                  website = COALESCE(website, 'https://www.chromasonic.com/'), hours_text = 'By appointment only',
                  osm_type = NULL, osm_id = NULL, review_status = 'ok'
    WHERE name = 'Satellite One';
UPDATE places SET address_text = '7001 Franklin Avenue, Los Angeles, California 90028', geom = pg_temp.pt(-118.3121446, 34.1053858),
                  website = COALESCE(website, 'https://www.magiccastle.com/'), osm_type = NULL, osm_id = NULL
    WHERE name = 'The Magic Castle';  -- stays needs_review: the address is not from its page
UPDATE places SET name = 'Highline Adventures', address_text = '700 East Highway 246, Buellton, California 93427',
                  geom = pg_temp.pt(-120.2001965, 34.6158638), phone = '+1-805-556-4049',
                  website = 'https://highlineadventures.com/', osm_type = NULL, osm_id = NULL, review_status = 'ok'
    WHERE name = 'Epic Sights';
UPDATE places SET website = NULL, category = 'arts' WHERE name = 'Hollywood Pantages Theatre';  -- site was Portland's Hollywood Theatre
UPDATE places SET address_text = '10100 Jefferson Boulevard, Culver City, California 90232', geom = pg_temp.pt(-118.388794, 34.0122751)
    WHERE name = 'Mr. Bones Pumpkin Patch';
UPDATE events SET address_text = '10100 Jefferson Boulevard, Culver City, California 90232'
    WHERE place_id = pg_temp.pid('Mr. Bones Pumpkin Patch');

\echo == after
SELECT (SELECT count(*) FROM places) AS places, (SELECT count(*) FROM events) AS events,
       (SELECT count(*) FROM item_sources) AS item_sources;
\echo == events without a place (should be none)
SELECT title FROM events WHERE place_id IS NULL;
\echo == events whose place coordinates differ from their own by over 300 m (should be none)
SELECT e.title, p.name FROM events e JOIN places p ON p.id = e.place_id WHERE ST_Distance(e.geom, p.geom) > 300;
\echo == places still to re-check with the resolver (street-only or city-only addresses, left as they are)
SELECT name, address_text FROM places
    WHERE address_text !~ '^[0-9]' OR address_text !~ ',' ORDER BY name;

\if :{?commit}
    \echo == COMMITTING
    COMMIT;
\else
    \echo == DRY RUN, rolling back. Run again with -v commit=1 to keep the changes
    ROLLBACK;
\endif
