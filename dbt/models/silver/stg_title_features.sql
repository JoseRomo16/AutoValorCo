{{ config(materialized='view') }}

-- Everything we can mine out of the listing title, at no extra request cost.
--
-- The search card carries only year and mileage as structured fields, so make, model
-- and engine size have to come from the title. The F1 pilot showed these are the
-- dominant price drivers: without them R2 is 0.36 for cars and 0.11 for motorcycles.
--
-- DuckDB uses RE2, which has no lookbehind, so ambiguous numbers are removed from the
-- text first rather than excluded by the pattern.
--
-- The model token is mined by scanning the title left to right over three seeds, and the
-- rules differ **by vertical** because the same string means different things: "1.6" is a
-- displacement on a car and nothing on a motorcycle, while a bare number is a real
-- motorcycle model (KTM 390, BMW 1200) and never a car model.

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

-- A title may contain several aliases ("Honda Xre 300 tipo Bajaj"), so each candidate is
-- ranked. The order matters and each level earns its place:
--
--   1. A manufacturer beats a distributor, which beats a model name.
--
--      Manufacturer over distributor is what resolves "Akt Voge Ds300" and "Auteco Kymco
--      Twist 125": AKT, Victory and Auteco sell other makes' bikes alongside their own,
--      so when a title names both, the one that built the vehicle is the answer. The
--      distributors keep their own listings, because a title that names no other make
--      still ranks them first.
--
--      Make over model name is what makes the model aliases strictly additive. Roughly a
--      fifth of motorcycle titles never name their make, so the seed also maps model
--      names to the make that builds them -- but "Suzuki ... Agility" must stay a Suzuki
--      rather than becoming a Kymco because the model alias happens to be longer. A model
--      alias can therefore only fire on a title where no make was found at all.
--   2. An alias at the start of the title wins, since that is where the make usually is.
--   3. The longest alias wins, which keeps "mercedes benz" ahead of "mercedes".
brand_candidates as (

    select
        cleaned.listing_id,
        brands.brand,
        brands.alias,
        brands.alias_kind,
        row_number() over (
            partition by cleaned.listing_id
            order by
                case when brands.alias_kind = 'brand' then brands.brand_rank else 2 end,
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

-- Every make alias the title matched, not only the winning one, so the make can be taken
-- out of the text before the model is read off it. A single-token alias is also dropped
-- token by token further down -- that is what catches a make written twice ("Mazda Mazda
-- 2"), where the first removal eats the delimiter the second match needed. This pass is
-- what handles the aliases that span two words: without it "Land Rover Range Rover
-- Evoque" hands back "land rover" as the model for all 35 of them.
matched_brand_aliases as (

    select
        cleaned.listing_id,
        -- Longest first, and that order is load-bearing. "Mercedes-Benz Clase C" matches
        -- both `mercedes` and `mercedes-benz`; removing the short one first eats the
        -- delimiter the long one needed and leaves "benz" as the model for all 481 of
        -- them. Same shape on "Can Am Maverick", which left "am" on 40 listings.
        list(brands.alias order by length(brands.alias) desc) as aliases
    from cleaned
    inner join {{ ref('vehicle_brands') }} as brands
        on brands.applies_to in ('both', cleaned.vehicle_type)
        and brands.alias_kind = 'brand'
        and regexp_matches(
            lower(cleaned.title), '(^|[^a-z])' || brands.alias || '([^a-z]|$)'
        )
    group by cleaned.listing_id

),

resolved_brand as (

    select
        listing_id,
        brand,
        -- When the make was recognised *through* a model name, that name is the model --
        -- no guessing needed. The token scan below is the fallback for titles that named
        -- their make outright.
        case when alias_kind = 'model' then alias end as model_from_alias
    from brand_candidates
    where candidate_rank = 1

),

-- The three token lists, collapsed to one row so the scan below can reach them without a
-- correlated subquery inside a lambda.
--
-- Make names are dropped as model tokens from the same seed that resolves them, rather
-- than from a hand-kept copy: a title that repeats its make ("Mazda Mazda 2") or spells it
-- across two words ("Cf Moto 700", "Citroën C4") otherwise hands the make itself back as
-- the model. Only `brand`-kind aliases are dropped -- a `model`-kind alias *is* a model
-- ("Suzuki Gs 500" keeps "gs").
token_rules as (

    select
        list(token) filter (where rule = 'drop' and applies_to in ('both', 'car'))
            as car_drop,
        list(token) filter (where rule = 'drop' and applies_to in ('both', 'motorcycle'))
            as motorcycle_drop,
        list(token) filter (where rule = 'join' and applies_to in ('both', 'car'))
            as car_join,
        list(token) filter (where rule = 'join' and applies_to in ('both', 'motorcycle'))
            as motorcycle_join
    from {{ ref('model_tokens') }}

),

brand_words as (

    select
        list(alias) filter (where applies_to in ('both', 'car')) as car_words,
        list(alias) filter (where applies_to in ('both', 'motorcycle')) as motorcycle_words
    from {{ ref('vehicle_brands') }}
    where alias_kind = 'brand'
      -- A multi-word alias cannot be matched token by token; the second word of the ones
      -- that actually collide ("great wall", "mercedes benz") is a `drop` token instead.
      and not contains(alias, ' ')

),

tokenised as (

    select
        cleaned.listing_id,
        cleaned.vehicle_type,
        cleaned.title,
        cleaned.searchable,
        resolved_brand.brand,
        resolved_brand.model_from_alias,
        list_filter(
            list_transform(
                str_split(
                    -- Anything that is not a letter, a digit, a dot or a dash separates
                    -- tokens, so punctuation stuck to a token ("f800gs,", "r15/",
                    -- "**características:**") stops creating a level of its own.
                    regexp_replace(
                        coalesce(
                            list_reduce(
                                list_prepend(cleaned.searchable, matched.aliases),
                                (text, alias) -> regexp_replace(
                                    text, '(^|[^a-z])' || alias || '([^a-z]|$)', ' ', 'g'
                                )
                            ),
                            cleaned.searchable
                        ),
                        '[^a-z0-9áéíóúüñ.-]+',
                        ' ',
                        'g'
                    ),
                    ' '
                ),
                -- Inner dots and dashes are part of the name ("mt-09", "1.6"); leading and
                -- trailing ones are leftovers ("mt15-", "-").
                token -> regexp_replace(token, '^[.-]+|[.-]+$', '', 'g')
            ),
            token -> token <> ''
        ) as raw_tokens
    from cleaned
    left join resolved_brand on resolved_brand.listing_id = cleaned.listing_id
    left join matched_brand_aliases as matched on matched.listing_id = cleaned.listing_id

),

scanned as (

    select
        tokenised.*,
        list_filter(
            tokenised.raw_tokens,
            token -> not list_contains(
                case
                    when tokenised.vehicle_type = 'car' then token_rules.car_drop
                    else token_rules.motorcycle_drop
                end,
                token
            )
            and not list_contains(
                case
                    when tokenised.vehicle_type = 'car' then brand_words.car_words
                    else brand_words.motorcycle_words
                end,
                token
            )
            -- Cars advertise their displacement in litres, so "1.6" is never a model.
            -- Motorcycles advertise cc, where a bare number *is* the model, which is why
            -- this is scoped to one vertical instead of being a general rule.
            and not (tokenised.vehicle_type = 'car' and regexp_matches(token, '^[0-9][.,][0-9]$'))
            -- A second year in the title ("Modelo 2027" on a 2026 listing) survives the
            -- model_year removal above. No motorcycle model is a four-digit number in
            -- that range -- the largest are KTM's 1390 and BMW's 1300 -- so dropping it
            -- is safe here. It is not safe for cars, where Peugeot sells a 2008.
            and not (
                tokenised.vehicle_type = 'motorcycle'
                and regexp_matches(token, '^(19|20)[0-9]{2}$')
            )
        ) as model_tokens,
        case
            when tokenised.vehicle_type = 'car' then token_rules.car_join
            else token_rules.motorcycle_join
        end as join_tokens
    from tokenised
    cross join token_rules
    cross join brand_words

),

mined as (

    select
        listing_id,
        vehicle_type,
        title,
        searchable,
        brand,
        model_from_alias,
        -- A family word is never a model on its own: "Clase" covers every Mercedes-Benz
        -- from an A 200 to a GLE 450, and 405 of 480 listings came out carrying it. The
        -- word plus the token after it ("clase gle", "serie 2", "land cruiser",
        -- "model 3") is the level that separates them.
        case
            when model_tokens[1] is null then null
            when list_contains(join_tokens, model_tokens[1]) and model_tokens[2] is not null
                then model_tokens[1] || ' ' || model_tokens[2]
            else model_tokens[1]
        end as model_token
    from scanned

),

engine as (

    select
        mined.*,
        -- Cars advertise litres ("1.6"); motorcycles advertise cc, sometimes spelled
        -- out ("690cc") and otherwise as part of the model name ("Xre 300", "G310").
        try_cast(regexp_extract(mined.searchable, '([0-9])[.,]([0-9])', 1) as bigint) * 1000
        + try_cast(regexp_extract(mined.searchable, '([0-9])[.,]([0-9])', 2) as bigint) * 100
            as litres_cc,
        try_cast(
            regexp_extract(mined.searchable, '([0-9]{2,4})\s*(cc|c\.c)', 1) as bigint
        ) as explicit_cc,
        list_max(
            list_filter(
                list_transform(
                    regexp_extract_all(mined.searchable, '[0-9]{2,4}'),
                    value -> try_cast(value as bigint)
                ),
                value -> value between {{ var('min_engine_cc') }} and {{ var('max_engine_cc') }}
            )
        ) as inferred_cc
    from mined

),

named as (

    select
        engine.*,
        coalesce(engine.model_from_alias, engine.model_token) as model_before_alias
    from engine

)

select
    named.listing_id,
    coalesce(named.brand, 'Desconocida') as brand,
    -- One spelling per model. The seed carries the duplicates and typos the lake actually
    -- holds ("mt03" and "mt-03", "himalaya" and "himlayan", "v-strom" through five
    -- spellings), scoped to a make where the token is only unambiguous under that make.
    coalesce(aliases.model, named.model_before_alias) as model,
    case
        when named.vehicle_type = 'car'
            then case
                when named.litres_cc between {{ var('min_car_cc') }} and {{ var('max_car_cc') }}
                    then named.litres_cc
            end
        -- An explicit "690cc" beats a number guessed from the model name, but it is
        -- still only a number someone typed, so it gets the same range check.
        else case
            when coalesce(named.explicit_cc, named.inferred_cc)
                between {{ var('min_engine_cc') }} and {{ var('max_engine_cc') }}
                then coalesce(named.explicit_cc, named.inferred_cc)
        end
    end as engine_cc,
    -- Quads, buggies and side-by-sides are listed as motorcycles but are a different
    -- market with a different price mechanism, so F2 can segment them out.
    named.vehicle_type = 'motorcycle'
    and (
        regexp_matches(
            lower(named.title),
            'cuatrimoto|cuatricicl|cuadricicl|buggy|buggi|utv|atv|side by side|rzr'
            || '|maverick|outlander|sportsman'
        )
        or coalesce(named.brand, '') = 'Polaris'
    ) as is_quad,
    -- Cargo three-wheelers are the other population inside the motorcycle vertical: a
    -- load-carrying body on a 200 cc engine prices like neither a motorcycle nor a quad.
    -- 11 listings today, so this is a flag for the model to split on rather than a
    -- correction worth expecting in the MAPE.
    named.vehicle_type = 'motorcycle'
    and regexp_matches(
        lower(named.title),
        'moto ?carro|moto ?carga|motofurgon|carguero|karguero|tricargo|tricimoto'
    ) as is_cargo
from named
left join {{ ref('model_aliases') }} as aliases
    on aliases.alias = named.model_before_alias
    and aliases.applies_to = named.vehicle_type
    and (aliases.brand is null or aliases.brand = named.brand)
