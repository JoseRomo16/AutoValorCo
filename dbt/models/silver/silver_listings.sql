-- One row per (listing, asking price): a listing that is re-captured unchanged
-- collapses into a single row, while a price change becomes a new row, which is what
-- the monthly price index needs.
--
-- Implausible rows are kept and flagged instead of dropped, so data quality stays
-- measurable. Filtering happens in gold.

with staged as (

    select * from {{ ref('stg_tucarro_listings') }}

),

deduplicated as (

    select
        listing_id,
        source,
        source_url,
        vehicle_type,
        title,
        price_cop,
        currency,
        model_year,
        mileage_km,
        city,
        department,
        is_official_store,
        min(captured_at) over listing_price as first_seen_at,
        max(captured_at) over listing_price as last_seen_at,
        count(*) over listing_price as capture_count
    from staged
    window listing_price as (partition by listing_id, price_cop)
    qualify row_number() over (
        partition by listing_id, price_cop order by captured_at desc
    ) = 1

),

flagged as (

    select
        *,
        case
            when price_cop is null then 'price_missing'
            when price_cop < {{ var('min_price_cop') }} then 'price_too_low'
            when price_cop > {{ var('max_price_cop') }} then 'price_too_high'
            when currency is not null and currency <> '$' then 'currency_not_cop'
            when model_year is null then 'model_year_missing'
            when model_year < {{ var('min_model_year') }} then 'model_year_too_old'
            -- Next year's models are legitimately on sale today; anything beyond
            -- that is a parsing error.
            when model_year > year(last_seen_at) + 1 then 'model_year_in_future'
            when mileage_km is null then 'mileage_missing'
            when mileage_km > {{ var('max_mileage_km') }} then 'mileage_too_high'
        end as invalid_reason
    from deduplicated

)

select
    listing_id,
    source,
    source_url,
    vehicle_type,
    title,
    price_cop,
    model_year,
    mileage_km,
    city,
    department,
    is_official_store,
    first_seen_at,
    last_seen_at,
    capture_count,
    invalid_reason is null as is_valid,
    invalid_reason
from flagged
