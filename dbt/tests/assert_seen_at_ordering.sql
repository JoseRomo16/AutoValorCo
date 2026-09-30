-- A listing cannot have been last seen before it was first seen.
select
    listing_id,
    first_seen_at,
    last_seen_at
from {{ ref('silver_listings') }}
where last_seen_at < first_seen_at
