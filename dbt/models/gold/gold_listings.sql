-- Model-ready table: only plausible rows, one row per listing (its latest asking
-- price), with the derived columns the models consume.
--
-- The target is log(price); valor_fasecolda is never joined in here, it is only a
-- benchmark (information leakage).

with valid as (

    select * from {{ ref('silver_listings') }}
    where is_valid
    qualify row_number() over (
        partition by listing_id order by last_seen_at desc, price_cop desc
    ) = 1

)

select
    listing_id,
    source_url,
    vehicle_type,
    title,
    price_cop,
    ln(price_cop) as log_price,
    model_year,
    greatest(year(last_seen_at) - model_year, 0) as vehicle_age_years,
    mileage_km,
    -- New and current-year vehicles divide by one year, so the column reads as
    -- "kilometres so far" rather than exploding towards infinity.
    mileage_km / greatest(year(last_seen_at) - model_year, 1) as km_per_year,
    city,
    department,
    is_official_store,
    first_seen_at,
    last_seen_at
from valid
