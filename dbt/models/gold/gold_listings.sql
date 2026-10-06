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
    -- The listing page wins when it has a displacement: it is a form field the seller
    -- filled in, while the title version is mined out of free text. Falls back to the
    -- title, so a listing with no detail row keeps exactly the value it had before.
    coalesce(details.detail_engine_cc, title_features.engine_cc) as engine_cc,
    coalesce(title_features.is_quad, false) as is_quad,

    -- Detail-page features. Null for every listing that has not been enriched, which
    -- both tree libraries route down their own branch, so "not enriched" stays a state
    -- rather than becoming an imputed average.
    details.detail_body_type as body_type,
    details.detail_transmission as transmission,
    details.detail_brakes as brakes,
    details.detail_color as color,
    details.detail_gear_count as gear_count,
    details.detail_single_owner as is_single_owner,
    details.listing_id is not null as has_detail,
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
left join {{ ref('stg_listing_details') }} as details
    on details.listing_id = valid.listing_id
