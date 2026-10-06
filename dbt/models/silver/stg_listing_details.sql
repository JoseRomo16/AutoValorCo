{{ config(materialized='view') }}

-- Typed columns out of the listing-page attribute table. One row per listing.
--
-- The enrichment is optional and incremental: a lake that has never run it has no
-- data/detail/ at all, and read_parquet errors on a glob that matches nothing. So the
-- source is probed with DuckDB's glob(), which returns zero rows instead of failing, and
-- the model falls back to a typed empty relation. gold_listings left-joins this, so an
-- un-enriched lake produces exactly the gold it produced before.

{%- set detail_glob = env_var('AUTOVALOR_DETAIL_GLOB', 'data/detail/**/*.parquet') -%}
{%- set has_details = false -%}
{%- if execute -%}
    {%- set probe = run_query("select count(*) as files from glob('" ~ detail_glob ~ "')") -%}
    {%- set has_details = probe.columns[0].values()[0] > 0 -%}
{%- endif -%}

{% if has_details %}

with detail as (

    select * from {{ source('detail', 'listings') }}

),

parsed as (

    select
        *,
        -- "150 cc" -> 150, ".' separators removed.
        try_cast(
            regexp_replace(
                replace(coalesce(json_extract_string(attributes_json, '$.engine_cc'), ''), '.', ''),
                '[^0-9]', '', 'g'
            ) as bigint
        ) as engine_cc_raw
    from detail

)

select
    listing_id,
    vehicle_type,
    fetched_at,

    -- The segment, and the reason this enrichment exists for motorcycles: a Naked, a
    -- Scooter and an Enduro at the same displacement are different price classes, and
    -- the title never says which.
    nullif(trim(json_extract_string(attributes_json, '$.body_type')), '') as detail_body_type,

    -- The title yields a displacement for 80,6 % of motorcycles; the page yields one for
    -- 94,9 %, so this is the column that fills the gap.
    --
    -- Bounded by the same plausibility window the title version is. The form field is
    -- free text, and the first production pass returned 0, 1, 11, 12, 13 and 40 cc: part
    -- typos, part electric motorcycles that have no displacement at all. Nulling them
    -- here lets gold's coalesce fall back to the title instead of poisoning a feature.
    -- The Pandera contract on gold is what caught this.
    case
        when engine_cc_raw between {{ var('min_engine_cc') }} and {{ var('max_engine_cc') }}
            then engine_cc_raw
    end as detail_engine_cc,

    nullif(trim(json_extract_string(attributes_json, '$.color')), '') as detail_color,
    nullif(trim(json_extract_string(attributes_json, '$.brakes')), '') as detail_brakes,
    nullif(trim(json_extract_string(attributes_json, '$.transmission')), '') as detail_transmission,

    -- "24 W", "11 hp": the unit is inconsistent across adverts, so the number alone is
    -- not comparable. Kept as the published string until there is a reason to trust it.
    nullif(trim(json_extract_string(attributes_json, '$.power')), '') as detail_power_raw,

    -- Free text as well, and the first pass returned 0 and 82 among the real values.
    case
        when try_cast(json_extract_string(attributes_json, '$.gear_count') as bigint)
            between {{ var('min_gear_count') }} and {{ var('max_gear_count') }}
            then try_cast(json_extract_string(attributes_json, '$.gear_count') as bigint)
    end as detail_gear_count,

    case json_extract_string(attributes_json, '$.single_owner')
        when 'Sí' then true
        when 'No' then false
    end as detail_single_owner,

    -- The brand and model as the seller filled the form in, which is cleaner than the
    -- token mined out of the free-text title.
    nullif(trim(json_extract_string(attributes_json, '$.brand')), '') as detail_brand,
    nullif(trim(json_extract_string(attributes_json, '$.model')), '') as detail_model

from parsed

{% else %}

-- No enrichment pass yet: the same columns, no rows.
select
    cast(null as varchar) as listing_id,
    cast(null as varchar) as vehicle_type,
    cast(null as timestamp with time zone) as fetched_at,
    cast(null as varchar) as detail_body_type,
    cast(null as bigint) as detail_engine_cc,
    cast(null as varchar) as detail_color,
    cast(null as varchar) as detail_brakes,
    cast(null as varchar) as detail_transmission,
    cast(null as varchar) as detail_power_raw,
    cast(null as bigint) as detail_gear_count,
    cast(null as boolean) as detail_single_owner,
    cast(null as varchar) as detail_brand,
    cast(null as varchar) as detail_model
where false

{% endif %}
