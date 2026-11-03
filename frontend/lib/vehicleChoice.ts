"use client";

/**
 * Which vertical the market page shows, shared by every section and remembered.
 *
 * Choosing Motos in one section switches all of them: comparing depreciation with retained
 * value for the same vehicles is the reason the sections sit together. The choice persists
 * in `localStorage` as a convenience only; a private window or blocked storage falls back
 * to cars without breaking anything.
 */

import { useSyncExternalStore } from "react";

import type { VehicleType } from "./results";

const STORAGE_KEY = "autovalor.market.vehicle";
const DEFAULT: VehicleType = "car";

const listeners = new Set<() => void>();
let memory: VehicleType = DEFAULT;

function read(): VehicleType {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "car" || stored === "motorcycle") return stored;
  } catch {
    // Storage unavailable: the in-memory choice still works for this page view.
  }
  return memory;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function chooseVehicle(vehicle: VehicleType): void {
  memory = vehicle;
  try {
    window.localStorage.setItem(STORAGE_KEY, vehicle);
  } catch {
    // Kept in memory only.
  }
  listeners.forEach((listener) => listener());
}

export function useVehicleChoice(): VehicleType {
  return useSyncExternalStore(subscribe, read, () => DEFAULT);
}
