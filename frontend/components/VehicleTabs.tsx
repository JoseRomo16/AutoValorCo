"use client";

/**
 * Cars / Motorcycles as tabs inside a market section.
 *
 * Every section's tabs read and write the same choice (`lib/vehicleChoice`), so switching
 * one switches all of them and the page keeps comparing the same vehicles. WAI-ARIA tabs:
 * arrow keys move between the two, and only the selected tab is in the tab order.
 *
 * Switching keeps the tapped tabs still on screen. Every section changes at once, and the
 * ones above can change height (depreciation has 12 car makes and 6 motorcycle makes), so
 * on a phone the page jumped by a few hundred pixels under the reader's finger. The tabs'
 * position is measured before and after the switch and the difference scrolled back.
 * Browsers that anchor scroll on their own would correct it too, so the dashboard opts
 * out of scroll anchoring and this is the only correction.
 */

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { flushSync } from "react-dom";

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
  const list = useRef<HTMLDivElement>(null);

  function select(next: VehicleType) {
    if (next === vehicle) return;
    const before = list.current?.getBoundingClientRect().top;
    // Render the switch now, so the layout below is the new one when it is measured.
    flushSync(() => chooseVehicle(next));
    const after = list.current?.getBoundingClientRect().top;
    if (before !== undefined && after !== undefined && after !== before) {
      // Instant: the page sets `scroll-behavior: smooth`, and an animated correction is
      // the very slide this removes.
      window.scrollBy({ top: after - before, behavior: "instant" });
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const next = VEHICLES[(VEHICLES.indexOf(vehicle) + 1) % VEHICLES.length] as VehicleType;
    select(next);
    tabs.current[VEHICLES.indexOf(next)]?.focus({ preventScroll: true });
  }

  return (
    <div>
      <div
        ref={list}
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
              onClick={() => select(candidate)}
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
