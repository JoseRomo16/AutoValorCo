"use client";

/**
 * Which makes the retained-value chart compares, per vertical, remembered.
 *
 * `null` for a vertical means "the defaults" (the make that holds most, the one that holds
 * least, the reference); an empty list is a choice too, after "clear all". Stored in
 * `localStorage` as a convenience only: a private window or blocked storage keeps the
 * choice in memory for the page view and starts from the defaults next time.
 */

import { useMemo, useSyncExternalStore } from "react";

import type { VehicleType } from "./results";

export type BrandSelection = Record<VehicleType, string[] | null>;

const STORAGE_KEY = "autovalor.market.brands";
const EMPTY: BrandSelection = { car: null, motorcycle: null };

const listeners = new Set<() => void>();
let memory = "";

function read(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? memory;
  } catch {
    return memory;
  }
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function parse(raw: string): BrandSelection {
  if (raw === "") return EMPTY;
  try {
    const value = JSON.parse(raw) as Partial<Record<VehicleType, unknown>>;
    const list = (entry: unknown) =>
      Array.isArray(entry) && entry.every((item) => typeof item === "string")
        ? (entry as string[])
        : null;
    return { car: list(value.car), motorcycle: list(value.motorcycle) };
  } catch {
    return EMPTY;
  }
}

/**
 * The stored choice for a vertical at this instant, not as of the last render.
 *
 * A toggle has to start from here: two taps landing before React re-renders would both
 * start from the same rendered list and the second would undo the first.
 */
export function currentBrands(vertical: VehicleType): string[] | null {
  return parse(read())[vertical];
}

export function setBrands(vertical: VehicleType, brands: string[] | null): void {
  const next = { ...parse(read()), [vertical]: brands };
  memory = JSON.stringify(next);
  try {
    window.localStorage.setItem(STORAGE_KEY, memory);
  } catch {
    // Kept in memory only.
  }
  listeners.forEach((listener) => listener());
}

/** Test hook: forget every choice, in memory and in storage. */
export function resetBrands(): void {
  memory = "";
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored.
  }
  listeners.forEach((listener) => listener());
}

export function useBrandSelection(): BrandSelection {
  const raw = useSyncExternalStore(subscribe, read, () => "");
  return useMemo(() => parse(raw), [raw]);
}
