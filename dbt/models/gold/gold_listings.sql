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
    valid.listing_id,
    valid.source_url,
    valid.vehicle_type,
    valid.title,
    coalesce(title_features.brand, 'Desconocida') as brand,
    title_features.model,
    title_features.engine_cc,
    coalesce(title_features.is_quad, false) as is_quad,
    valid.price_cop,
    ln(valid.price_cop) as log_price,
    valid.model_year,
    greatest(year(valid.last_seen_at) - valid.model_year, 0) as vehicle_age_years,
    valid.mileage_km,
    -- New and current-year vehicles divide by one year, so the column reads as
    -- "kilometres so far" rather than exploding towards infinity.
    valid.mileage_km / greatest(year(valid.last_seen_at) - valid.model_year, 1) as km_per_year,
    valid.city,
    valid.department,
    valid.is_official_store,
    valid.first_seen_at,
    valid.last_seen_at
from valid
left join {{ ref('stg_title_features') }} as title_features
    on title_features.listing_id = valid.listing_id
