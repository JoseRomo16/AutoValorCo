{{ config(materialized='view') }}

-- Parse the raw strings captured from TuCarro into typed columns.
-- One row per listing per capture; deduplication happens in silver_listings.

with bronze as (

    select * from {{ source('bronze', 'listings') }}

)

select
    listing_id,
    source,
    source_url,
    captured_at,
    vehicle_type,
    nullif(trim(title), '') as title,

    -- The card's aria-label carries the amount without thousand separators, which is
    -- the most reliable source. The displayed price is the fallback.
    coalesce(
        try_cast(
            regexp_extract(
                json_extract_string(attributes_json, '$.price_aria_label'), '\d+'
            ) as bigint
        ),
        try_cast(replace(coalesce(price_raw, ''), '.', '') as bigint)
    ) as price_cop,

    nullif(trim(currency), '') as currency,

    try_cast(model_year_raw as bigint) as model_year,

    -- "86.000 Km" -> 86000, "0 Km" -> 0
    try_cast(
        regexp_replace(replace(coalesce(mileage_raw, ''), '.', ''), '[^0-9]', '', 'g') as bigint
    ) as mileage_km,

    -- "Chapinero - Bogotá D.C." -> city, department
    nullif(trim(split_part(coalesce(location_raw, ''), ' - ', 1)), '') as city,
    nullif(trim(split_part(coalesce(location_raw, ''), ' - ', 2)), '') as department,

    coalesce(
        json_extract_string(attributes_json, '$.official_store') = 'true', false
    ) as is_official_store

from bronze
