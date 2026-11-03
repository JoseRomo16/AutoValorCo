"use client";

/**
 * Cars / Motorcycles as tabs inside a market section.
 *
 * Every section's tabs read and write the same choice (`lib/vehicleChoice`), so switching
 * one switches all of them and the page keeps comparing the same vehicles. WAI-ARIA tabs:
 * arrow keys move between the two, and only the selected tab is in the tab order.
 */

import { useRef, type KeyboardEvent, type ReactNode } from "react";

import { useLang } from "./LanguageProvider";
import { copy } from "@/lib/i18n";
import type { VehicleType } from "@/lib/results";
import { chooseVehicle, useVehicleChoice } from "@/lib/vehicleChoice";

const VEHICLES: VehicleType[] = ["car", "motorcycle"];

export function VehicleTabs({
  id,
  children,
}: {
  /** Unique per section: the tab and panel ids hang off it. */
  id: string;
  children: (vehicle: VehicleType) => ReactNode;
}) {
  const { t } = useLang();
  const vehicle = useVehicleChoice();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const next = VEHICLES[(VEHICLES.indexOf(vehicle) + 1) % VEHICLES.length] as VehicleType;
    chooseVehicle(next);
    tabs.current[VEHICLES.indexOf(next)]?.focus();
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label={t(copy.form.vehicleType)}
        onKeyDown={onKeyDown}
        className="mb-6 inline-flex rounded-md border border-line p-0.5"
      >
        {VEHICLES.map((candidate, index) => {
          const selected = candidate === vehicle;
          return (
            <button
              key={candidate}
              ref={(node) => {
                tabs.current[index] = node;
              }}
              type="button"
              role="tab"
              id={`${id}-tab-${candidate}`}
              aria-selected={selected}
              aria-controls={`${id}-panel`}
              tabIndex={selected ? 0 : -1}
              onClick={() => chooseVehicle(candidate)}
              className={`min-h-10 rounded px-4 text-sm font-medium transition-colors duration-150 ${
                selected ? "bg-ink text-ground" : "text-muted hover:text-ink"
              }`}
            >
              {t(candidate === "car" ? copy.form.cars : copy.form.motorcycles)}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${vehicle}`}>
        {children(vehicle)}
      </div>
    </div>
  );
}
