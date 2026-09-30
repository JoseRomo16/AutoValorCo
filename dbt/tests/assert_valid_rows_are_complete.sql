-- A row flagged as valid must have every column the models need.
select
    listing_id,
    price_cop,
    model_year,
    mileage_km
from {{ ref('silver_listings') }}
where is_valid
  and (price_cop is null or model_year is null or mileage_km is null)
