{{ config(materialized='view') }}

-- Everything we can mine out of the listing title, at no extra request cost.
--
-- The search card carries only year and mileage as structured fields, so make, model
-- and engine size have to come from the title. The F1 pilot showed these are the
-- dominant price drivers: without them R2 is 0.36 for cars and 0.11 for motorcycles.
--
-- DuckDB uses RE2, which has no lookbehind, so ambiguous numbers are removed from the
-- text first rather than excluded by the pattern.

with listings as (

    select listing_id, vehicle_type, title, model_year
    from {{ ref('silver_listings') }}
    where title is not null
    -- One row per listing, which is the grain gold joins this on.
    --
    -- silver_listings is one row per (listing, asking price) on purpose: a price change
    -- becomes a new row, which is what the monthly index needs. So a listing whose price
    -- moved between captures arrives here more than once, and the join into gold would
    -- fan out. It stayed invisible while the lake held a single capture window; the first
    -- time the history spanned five days, 224 listings had repriced.
    --
    -- The tie-break matches gold's exactly, so the title mined here belongs to the same
    -- row gold keeps rather than to an older price.
    qualify row_number() over (
        partition by listing_id order by last_seen_at desc, price_cop desc
    ) = 1

),

cleaned as (

    select
        listing_id,
        vehicle_type,
        title,
        -- Drop the model year and any thousands-separated number ("26.000 Km"), so
        -- neither can be mistaken for an engine size.
        regexp_replace(
            regexp_replace(lower(title), '[0-9]+\.[0-9]{3}', ' ', 'g'),
            coalesce(model_year::varchar, '~none~'),
            ' ',
            'g'
        ) as searchable
    from listings

),

-- A title may contain several make aliases ("Honda Xre 300 tipo Bajaj"), so each
-- candidate is ranked: an alias at the start of the title wins, then the longest one,
-- which keeps "mercedes benz" ahead of "mercedes".
brand_candidates as (

    select
        cleaned.listing_id,
        brands.brand,
        row_number() over (
            partition by cleaned.listing_id
            order by
                case when lower(cleaned.title) like brands.alias || '%' then 0 else 1 end,
                length(brands.alias) desc
        ) as candidate_rank
    from cleaned
    inner join {{ ref('vehicle_brands') }} as brands
        on brands.applies_to in ('both', cleaned.vehicle_type)
        and regexp_matches(
            lower(cleaned.title), '(^|[^a-z])' || brands.alias || '([^a-z]|$)'
        )

),

resolved_brand as (

    select listing_id, brand
    from brand_candidates
    where candidate_rank = 1

),

engine as (

    select
        cleaned.listing_id,
        cleaned.vehicle_type,
        cleaned.title,
        cleaned.searchable,
        resolved_brand.brand,
        -- Cars advertise litres ("1.6"); motorcycles advertise cc, sometimes spelled
        -- out ("690cc") and otherwise as part of the model name ("Xre 300", "G310").
        try_cast(regexp_extract(cleaned.searchable, '([0-9])[.,]([0-9])', 1) as bigint) * 1000
        + try_cast(regexp_extract(cleaned.searchable, '([0-9])[.,]([0-9])', 2) as bigint) * 100
            as litres_cc,
        try_cast(
            regexp_extract(cleaned.searchable, '([0-9]{2,4})\s*(cc|c\.c)', 1) as bigint
        ) as explicit_cc,
        list_max(
            list_filter(
                list_transform(
                    regexp_extract_all(cleaned.searchable, '[0-9]{2,4}'),
                    value -> try_cast(value as bigint)
                ),
                value -> value between {{ var('min_engine_cc') }} and {{ var('max_engine_cc') }}
            )
        ) as inferred_cc
    from cleaned
    left join resolved_brand on resolved_brand.listing_id = cleaned.listing_id

)

select
    listing_id,
    coalesce(brand, 'Desconocida') as brand,
    -- The first token left after removing the make and the year is the model; the
    -- rest is trim detail that F2 can mine further.
    nullif(
        split_part(
            trim(
                regexp_replace(
                    regexp_replace(
                        searchable,
                        '(^|[^a-z])' || lower(coalesce(brand, '~none~')) || '([^a-z]|$)',
                        ' '
                    ),
                    '\s+',
                    ' ',
                    'g'
                )
            ),
            ' ',
            1
        ),
        ''
    ) as model,
    case
        when vehicle_type = 'car'
            then case
                when litres_cc between {{ var('min_car_cc') }} and {{ var('max_car_cc') }}
                    then litres_cc
            end
        -- An explicit "690cc" beats a number guessed from the model name, but it is
        -- still only a number someone typed, so it gets the same range check.
        else case
            when coalesce(explicit_cc, inferred_cc)
                between {{ var('min_engine_cc') }} and {{ var('max_engine_cc') }}
                then coalesce(explicit_cc, inferred_cc)
        end
    end as engine_cc,
    -- Quads, buggies and side-by-sides are listed as motorcycles but are a different
    -- market with a different price mechanism, so F2 can segment them out.
    vehicle_type = 'motorcycle'
    and (
        regexp_matches(
            lower(title),
            'cuatrimoto|buggy|buggi|utv|atv|side by side|rzr|maverick|outlander|sportsman'
        )
        or coalesce(brand, '') = 'Polaris'
    ) as is_quad
from engine
