"use client";

/**
 * A numeric field that groups thousands while you type.
 *
 * `89000000` is unreadable and `89.000.000` is a price. The hard part is the caret: naive
 * reformatting on every keystroke sends it to the end, so editing the middle of a figure
 * becomes impossible. This counts the digits to the right of the caret, reformats, and puts
 * the caret back in front of the same digit — the separator count can change underneath it
 * and the position still lands where the person was typing.
 *
 * `type="text"` with `inputMode="numeric"`, not `type="number"`. A number input rejects the
 * grouped value outright, and its spinner and scroll-to-change behaviour are wrong for a
 * price. Validation lives in the form, which can explain itself; the browser's own
 * constraint UI cannot.
 */

import { useId, useState } from "react";

import { integer, parseGrouped } from "@/lib/format";
import type { Lang } from "@/lib/i18n";

export function NumberField({
  id,
  label,
  value,
  onChange,
  onBlur,
  lang,
  unit,
  prefix,
  placeholder,
  hint,
  error,
  disabled = false,
  optionalLabel,
  grouping = true,
  discardedLabel,
}: {
  id: string;
  label: string;
  /** The raw digits, with no separators. Empty string means unset. */
  value: string;
  onChange: (digits: string) => void;
  onBlur?: () => void;
  lang: Lang;
  /** Rendered inside the field, on the right: "km", "cc". */
  unit?: string;
  /** Rendered inside the field, on the left: "$". */
  prefix?: string;
  placeholder?: string;
  hint?: string;
  error?: string;
  disabled?: boolean;
  optionalLabel?: string;
  /**
   * Group thousands while typing. True for amounts, false for a year.
   *
   * A price needs the separators to be readable at eight digits. A year is four digits
   * that are never grouped in either language, and grouping them rendered 2024 as
   * "2.024", which reads as a different kind of number entirely.
   */
  grouping?: boolean;
  /**
   * Name the characters the mask could not use, in the reader's language.
   *
   * Passed in rather than built here so this stays a presentational component, the same
   * way `Combobox` takes its `emptyText`.
   */
  discardedLabel?: (characters: string) => string;
}) {
  const hintId = useId();
  /**
   * What the last keystroke threw away, if anything.
   *
   * A notice, deliberately not an error: the value that landed is usable and submission is
   * not blocked. It only answers "where did the rest of what I typed go?", which the field
   * used to leave unanswered.
   */
  const [discarded, setDiscarded] = useState("");

  const present = (digits: string) =>
    digits === "" ? "" : grouping ? integer(Number(digits), lang) : digits;
  const shown = present(value);

  function handle(event: React.ChangeEvent<HTMLInputElement>) {
    const input = event.target;
    const caretFromEnd = input.value.length - (input.selectionEnd ?? input.value.length);
    const digitsAfterCaret = input.value.slice(input.value.length - caretFromEnd).replace(/\D/g, "")
      .length;

    const { digits, discarded: dropped } = parseGrouped(input.value, lang);
    setDiscarded(dropped);
    onChange(digits);

    const formatted = present(digits);
    let position = formatted.length;
    let seen = 0;
    while (position > 0 && seen < digitsAfterCaret) {
      position -= 1;
      if (/\d/.test(formatted[position] ?? "")) seen += 1;
    }
    // React rewrites `value` after this handler, so the caret has to be restored once the
    // new value is in the DOM.
    window.requestAnimationFrame(() => input.setSelectionRange(position, position));
  }

  // An error outranks the notice: a value that breaks a rule is the more useful thing to
  // say, and two messages under one field is noise.
  const notice = error || discarded === "" || !discardedLabel ? null : discardedLabel(discarded);

  const describedBy = [
    error ? `${hintId}-error` : null,
    notice ? `${hintId}-notice` : null,
    hint ? `${hintId}-hint` : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1.5 block text-base font-medium">
        {label}
        {optionalLabel && <span className="ml-1.5 font-normal text-faint">{optionalLabel}</span>}
      </label>

      <div className="relative">
        {prefix && (
          <span
            aria-hidden
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 font-mono text-sm text-faint"
          >
            {prefix}
          </span>
        )}
        <input
          id={id}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          disabled={disabled}
          placeholder={placeholder}
          value={shown}
          onChange={handle}
          onBlur={onBlur}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          className={`h-12 w-full rounded-md border bg-ground font-mono text-base tabular-nums transition-[border-color,box-shadow] duration-200 placeholder:font-sans placeholder:text-faint focus:outline-none disabled:opacity-60 ${
            prefix ? "pl-8" : "pl-3.5"
          } ${unit ? "pr-12" : "pr-3.5"} ${
            error
              ? "border-bad"
              : "border-line-strong focus:border-accent-text focus:ring-3 focus:ring-accent-text/25"
          }`}
        />
        {unit && (
          <span
            aria-hidden
            className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 font-mono text-sm text-faint"
          >
            {unit}
          </span>
        )}
      </div>

      {error ? (
        <p id={`${hintId}-error`} className="mt-1.5 text-detail text-bad">
          {error}
        </p>
      ) : notice ? (
        // `role="status"` so it is announced when it appears: the whole point is that the
        // field no longer changes what was typed without saying so.
        <p id={`${hintId}-notice`} role="status" className="mt-1.5 text-detail text-muted">
          {notice}
        </p>
      ) : (
        hint && (
          <p id={`${hintId}-hint`} className="mt-1.5 text-detail text-muted">
            {hint}
          </p>
        )
      )}
    </div>
  );
}
