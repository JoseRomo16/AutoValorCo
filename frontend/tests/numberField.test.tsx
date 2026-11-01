import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { NumberField } from "@/components/ui/NumberField";
import type { Lang } from "@/lib/i18n";

/**
 * A controlled host, because the mask only makes sense as a round trip: the field reports
 * digits, the parent stores them, and the field re-renders them formatted. Asserting on
 * `onChange` alone would miss what the person actually sees.
 */
function Host({
  lang = "es",
  grouping,
  initial = "",
}: {
  lang?: Lang;
  grouping?: boolean;
  initial?: string;
}) {
  const [value, setValue] = useState(initial);
  return (
    <NumberField
      id="field"
      lang={lang}
      label="Campo"
      value={value}
      onChange={setValue}
      grouping={grouping}
      discardedLabel={(characters) => `Quitamos ${characters} porque no son números.`}
    />
  );
}

const field = () => screen.getByLabelText("Campo") as HTMLInputElement;

/** What a paste looks like to a controlled input: one change with the whole new value. */
const type = (text: string) => fireEvent.change(field(), { target: { value: text } });

describe("NumberField grouping", () => {
  it("does not group a year", () => {
    // The reported bug: typing 2024 showed "2.024".
    render(<Host grouping={false} />);
    type("2024");
    expect(field().value).toBe("2024");
  });

  it("still groups an amount", () => {
    render(<Host />);
    type("45000000");
    expect(field().value).toBe("45.000.000");
  });

  it("groups in the reader's locale", () => {
    render(<Host lang="en" />);
    type("45000000");
    expect(field().value).toBe("45,000,000");
  });
});

describe("NumberField paste handling", () => {
  it("reads a pasted amount with cents as the amount", () => {
    // Used to become 4.500.000.000: a hundred times the pasted value, silently.
    render(<Host />);
    type("45.000.000,00");
    expect(field().value).toBe("45.000.000");
  });

  it("reads a pasted amount without cents the same way", () => {
    render(<Host />);
    type("45.000.000");
    expect(field().value).toBe("45.000.000");
  });

  it("keeps a thousands group as thousands", () => {
    render(<Host />);
    type("45.000");
    expect(field().value).toBe("45.000");
  });
});

describe("NumberField discarded characters", () => {
  it("says what it threw away instead of deleting it in silence", () => {
    // "-5e9" became "$ 59" with no explanation at all.
    render(<Host />);
    type("-5e9");
    expect(field().value).toBe("59");
    expect(screen.getByRole("status")).toHaveTextContent("Quitamos -e porque no son números.");
  });

  it("says nothing when nothing was thrown away", () => {
    render(<Host />);
    type("45000");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("does not complain about discarded cents", () => {
    // The value is still the one that was pasted, so there is nothing to warn about.
    render(<Host />);
    type("45.000.000,00");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("clears the notice once the field is valid again", () => {
    render(<Host />);
    type("-5e9");
    expect(screen.queryByRole("status")).not.toBeNull();
    type("45000");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("lets an error outrank the notice", () => {
    // Two messages under one field is noise, and the rule is the more useful one.
    render(
      <NumberField
        id="field"
        lang="es"
        label="Campo"
        value="59"
        onChange={() => {}}
        error="Escribe el precio en pesos."
        discardedLabel={(characters) => `Quitamos ${characters}.`}
      />,
    );
    expect(screen.getByText("Escribe el precio en pesos.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("points the field at its notice for assistive technology", () => {
    render(<Host />);
    type("-5e9");
    const described = field().getAttribute("aria-describedby") ?? "";
    expect(described).not.toBe("");
    const notice = screen.getByRole("status");
    expect(described.split(" ")).toContain(notice.id);
  });
});
