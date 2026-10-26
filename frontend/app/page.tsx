import { ValuationForm } from "@/components/ValuationForm";
import { ValueHero } from "@/components/ValueHero";
import { manifest, servedModels } from "@/lib/results";

/**
 * The valuation page.
 *
 * The trust figures in the hero are read from `model.json` and the results manifest at
 * build time, not from the API: they describe the model inside the deployed image, so
 * fetching them would cost a cold start to learn something the repository already knows.
 * The form below is the only part of the site that talks to the service.
 */
export default function ValuePage() {
  const models = servedModels();
  const car = models.find((model) => model.vehicle_type === "car");
  const motorcycle = models.find((model) => model.vehicle_type === "motorcycle");
  const captures = manifest().capture_dates;

  if (!car || !motorcycle) {
    throw new Error("both bundles must be exported before the valuation page can be built");
  }

  return (
    <>
      <ValueHero
        facts={{
          listings: car.trained_on_rows + motorcycle.trained_on_rows,
          carMape: car.mape,
          motorcycleMape: motorcycle.mape,
          lastCapture: captures.at(-1) ?? "",
        }}
      />
      <ValuationForm />
    </>
  );
}
