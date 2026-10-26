"use client";

/**
 * A searchable single-select, built on the WAI-ARIA 1.2 combobox pattern.
 *
 * Written by hand rather than installed. The catalogue has about 60 car makes and over 800
 * motorcycle model tokens, so a native `<select>` means scrolling a list nobody can scan;
 * but a dependency for one control would be the largest thing in the bundle of a site whose
 * whole point is that it is free to serve.
 *
 * Three behaviours matter more than they look:
 *
 * **Matching ignores accents and case.** Someone typing "bogota" or "QUINDIO" is looking
 * for "Bogotá D.C." and "Quindío". A substring match on the raw string would fail both, and
 * the person would conclude the make is not in the list.
 *
 * **The list is ordered by how many listings back each option**, not alphabetically. The
 * make someone is most likely to own should be the first thing under the cursor, and the
 * count travels next to each option so the ordering explains itself.
 *
 * **The committed value is separate from the typed text.** `value` is what the model was
 * trained on and what gets sent; the input shows `display_name`. Typing without choosing
 * leaves the field uncommitted, and blurring restores the last committed label rather than
 * leaving a half-typed string that looks selected.
 */

import { useEffect, useId, useMemo, useRef, useState } from "react";

export type ComboOption = {
  /** What the model was trained on, and what gets sent. */
  value: string;
  /** The same level spelled for a reader. */
  label: string;
  /** Training listings behind this level; decides the order and is shown beside it. */
  count?: number;
  /** Options sharing a group are rendered together under its heading, in order. */
  group?: string;
};

/** Strip accents and case so "bogota" matches "Bogotá D.C.". */
function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

export function Combobox({
  id,
  label,
  options,
  value,
  onChange,
  placeholder,
  disabled = false,
  disabledHint,
  emptyText,
  countLabel,
  hint,
  error,
  required = false,
  optionalLabel,
}: {
  id: string;
  label: string;
  options: ComboOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  disabledHint?: string;
  /** Built from what was typed, so the message can quote it back. */
  emptyText: (query: string) => string;
  /** Renders the listing count beside an option, e.g. `(n) => "125 anuncios"`. */
  countLabel?: (count: number) => string;
  hint?: string;
  error?: string;
  required?: boolean;
  /** Shown beside the label when the field may be left empty, e.g. "opcional". */
  optionalLabel?: string;
}) {
  const listId = `${id}-list`;
  const hintId = useId();

  const selected = useMemo(
    () => options.find((option) => option.value === value),
    [options, value],
  );

  /**
   * `null` means "not typing", and the field then shows whatever is selected.
   *
   * Storing the committed label here instead would need an effect to re-sync it every time
   * the selection changed from outside -- choosing a make clears the model, and the model
   * field has to show that it was cleared. Deriving it removes that effect, and with it the
   * render where the field still displays a value that no longer exists.
   */
  const [typed, setTyped] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const query = typed ?? selected?.label ?? "";

  const matches = useMemo(() => {
    // An untouched field shows everything: the first interaction is as often "what is
    // available" as it is "find this one".
    if (typed === null) return options;
    const needle = fold(typed.trim());
    if (needle === "") return options;
    return options.filter((option) => fold(option.label).includes(needle));
  }, [options, typed]);

  // Keep the highlighted option in view when arrowing past the visible window.
  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function commit(option: ComboOption) {
    onChange(option.value);
    setTyped(null);
    setOpen(false);
  }

  function close() {
    setOpen(false);
    // Drop a half-typed string that was never committed, so the field never looks like it
    // holds a selection it does not.
    setTyped(null);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActive(0);
        return;
      }
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => Math.min(Math.max(current + step, 0), matches.length - 1));
    } else if (event.key === "Home" && open) {
      event.preventDefault();
      setActive(0);
    } else if (event.key === "End" && open) {
      event.preventDefault();
      setActive(matches.length - 1);
    } else if (event.key === "Enter") {
      const option = matches[active];
      if (open && option) {
        event.preventDefault();
        commit(option);
      }
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      close();
    }
  }

  /**
   * Which options open a new group, worked out once rather than by mutating a cursor while
   * rendering. The headings stay out of the option list itself, so `active` keeps indexing
   * a single flat array and the arrow keys never land on a heading.
   */
  const headings = useMemo(
    () => matches.map((option, index) => (option.group !== matches[index - 1]?.group ? option.group : undefined)),
    [matches],
  );

  const describedBy = [error ? `${hintId}-error` : null, hint ? `${hintId}-hint` : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium">
        {label}
        {!required && optionalLabel && (
          <span className="ml-1.5 font-normal text-faint">{optionalLabel}</span>
        )}
      </label>

      <div className="relative">
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && matches[active] ? `${id}-opt-${active}` : undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          placeholder={disabled ? disabledHint : placeholder}
          value={query}
          onChange={(event) => {
            setTyped(event.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => {
            setOpen(true);
            inputRef.current?.select();
          }}
          // `blur` rather than a document listener: it fires for both a click elsewhere and
          // a Tab, which is the whole set of ways focus can leave.
          onBlur={close}
          onKeyDown={onKeyDown}
          className={`h-12 w-full rounded-md border bg-ground px-3.5 text-base transition-[border-color,box-shadow] duration-200 placeholder:text-faint focus:outline-none disabled:opacity-60 ${
            error
              ? "border-bad"
              : "border-line-strong focus:border-accent-text focus:ring-3 focus:ring-accent-text/25"
          }`}
        />

        {open && !disabled && (
          <div
            ref={listRef}
            id={listId}
            role="listbox"
            aria-label={label}
            className="absolute inset-x-0 top-[calc(100%+4px)] z-20 max-h-[264px] overflow-y-auto rounded-md border border-line-strong bg-surface-2 p-1"
          >
            {matches.length === 0 && (
              <p className="px-2.5 py-3 text-sm text-muted">{emptyText(query.trim())}</p>
            )}
            {matches.map((option, index) => {
              const heading = headings[index];
              return (
                <div key={option.value}>
                  {heading && (
                    <p className="px-2.5 pb-1.5 pt-2.5 font-mono text-xs uppercase tracking-[0.08em] text-faint">
                      {heading}
                    </p>
                  )}
                  <div
                    id={`${id}-opt-${index}`}
                    role="option"
                    aria-selected={index === active}
                    // `mousedown` fires before `blur`, so the choice registers instead of
                    // the list closing out from under the pointer.
                    onMouseDown={(event) => {
                      event.preventDefault();
                      commit(option);
                    }}
                    onMouseEnter={() => setActive(index)}
                    className={`flex min-h-10 cursor-pointer items-center justify-between gap-3 rounded px-2.5 py-2 text-sm ${
                      index === active ? "bg-surface shadow-[inset_2px_0_0_var(--accent)]" : ""
                    }`}
                  >
                    <span className="min-w-0 truncate">{option.label}</span>
                    {option.count !== undefined && countLabel && (
                      <span className="shrink-0 font-mono text-xs text-faint">
                        {countLabel(option.count)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {error ? (
        <p id={`${hintId}-error`} className="mt-1.5 text-xs text-bad">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${hintId}-hint`} className="mt-1.5 text-xs text-muted">
            {hint}
          </p>
        )
      )}
    </div>
  );
}
