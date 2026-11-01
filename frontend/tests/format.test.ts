import { describe, expect, it } from "vitest";

import { integer, parseGrouped, separators } from "@/lib/format";

describe("separators", () => {
  it("reads the marks each locale actually uses", () => {
    expect(separators("es")).toEqual({ group: ".", decimal: "," });
    expect(separators("en")).toEqual({ group: ",", decimal: "." });
  });

  it("agrees with what integer() writes", () => {
    // These two have to match exactly: one parses what the other formats.
    expect(integer(45_000_000, "es")).toContain(separators("es").group);
    expect(integer(45_000_000, "en")).toContain(separators("en").group);
  });
});

describe("parseGrouped", () => {
  it("reads a pasted amount with cents as the amount, not a hundred times it", () => {
    // The reported bug: "45.000.000,00" became 4.500.000.000 because the comma was
    // stripped and the cents were concatenated as digits.
    expect(parseGrouped("45.000.000,00", "es").digits).toBe("45000000");
  });

  it("reads a pasted amount without cents the same way", () => {
    expect(parseGrouped("45.000.000", "es").digits).toBe("45000000");
  });

  it("does not mistake a thousands group for a decimal", () => {
    // "45.000" is forty-five thousand in Spanish, not forty-five.
    expect(parseGrouped("45.000", "es").digits).toBe("45000");
  });

  it("drops a fraction instead of appending it", () => {
    expect(parseGrouped("45,50", "es").digits).toBe("45");
    expect(parseGrouped("45.50", "en").digits).toBe("45");
  });

  it("handles the English shape on the English page", () => {
    expect(parseGrouped("45,000,000.00", "en").digits).toBe("45000000");
    expect(parseGrouped("45,000", "en").digits).toBe("45000");
  });

  it("reads a value pasted from the other locale rather than mangling it", () => {
    // A mark seen more than once is grouping, not a decimal: a number has at most one
    // decimal mark. So this is 45 million on the Spanish page, not 45.
    expect(parseGrouped("45,000,000", "es").digits).toBe("45000000");
    expect(parseGrouped("45.000.000", "en").digits).toBe("45000000");
  });

  it("reports characters it had to throw away", () => {
    // "-5e9" used to become "59" with nothing said about it.
    const { digits, discarded } = parseGrouped("-5e9", "es");
    expect(digits).toBe("59");
    expect(discarded).toBe("-e");
  });

  it("says nothing was discarded when nothing was", () => {
    expect(parseGrouped("45.000.000", "es").discarded).toBe("");
    expect(parseGrouped("", "es").discarded).toBe("");
  });

  it("does not count a dropped fraction as a discarded character", () => {
    // Cents are discarded on purpose and the value is still the one that was typed, so
    // there is nothing to warn about.
    expect(parseGrouped("45.000.000,00", "es").discarded).toBe("");
  });

  it("strips leading zeros so typing 0 then 5 reads five", () => {
    expect(parseGrouped("05", "es").digits).toBe("5");
    expect(parseGrouped("0", "es").digits).toBe("0");
  });

  it("returns empty for an empty field", () => {
    expect(parseGrouped("", "es").digits).toBe("");
  });
});
