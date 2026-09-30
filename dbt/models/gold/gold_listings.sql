-- Model-ready table: only plausible rows, one row per listing (its latest asking
-- price), with the derived columns the models consume.
--
-- The target is log(price); valor_fasecolda is never joined in here, it is only a
-- benchmark (information leakage).
--
-- Brand and model come out of the title, because the search card does not carry them
-- as structured fields. The F1 pilot showed they are the dominant price driver:
-- age and mileage alone leave sigma at 0.58 (cars) and 0.92 (motorcycles).

with valid as (

    select * from {{ ref('silver_listings') }}
    where is_valid
    qualify row_number() over (
        partition by listing_id order by last_seen_at desc, price_cop desc
    ) = 1

),

-- A title may contain several brand aliases ("Honda Xre 300 tipo Bajaj"), so each
-- candidate is ranked: an alias at the start of the title wins, then the longest one,
-- which keeps "mercedes benz" ahead of "mercedes".
brand_candidates as (

    select
        valid.listing_id,
        brands.brand,
        row_number() over (
            partition by valid.listing_id
            order by
                case when lower(valid.title) like brands.alias || '%' then 0 else 1 end,
                length(brands.alias) desc
        ) as candidate_rank
    from valid
    inner join {{ ref('vehicle_brands') }} as brands
        on brands.applies_to in ('both', valid.vehicle_type)
        and regexp_matches(
            lower(valid.title), '(^|[^a-z])' || brands.alias || '([^a-z]|$)'
        )
    where valid.title is not null

),

resolved as (

    select listing_id, brand
    from brand_candidates
    where candidate_rank = 1

),

with_brand as (

    select
        valid.*,
        coalesce(resolved.brand, 'Desconocida') as brand,
        -- Everything after the brand, minus the model year, gives the model and trim.
        -- The first token of that is the model; the rest is trim detail that F2 can
        -- mine further.
        nullif(
            trim(
                regexp_replace(
                    regexp_replace(lower(valid.title), '\d{4}', ' ', 'g'),
                    '(^|[^a-z])' || lower(coalesce(resolved.brand, '~none~')) || '([^a-z]|$)',
                    ' '
                )
            ),
            ''
        ) as model_text
    from valid
    left join resolved on resolved.listing_id = valid.listing_id

)

select
    listing_id,
    source_url,
    vehicle_type,
    title,
    brand,
    nullif(split_part(trim(regexp_replace(model_text, '\s+', ' ', 'g')), ' ', 1), '') as model,
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
from with_brand
