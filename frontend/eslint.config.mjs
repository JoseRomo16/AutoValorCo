import next from "eslint-config-next";

/**
 * Flat config. `next lint` was removed in Next 16, so CI runs eslint directly — see the
 * `lint` script in package.json.
 */
const config = [
  ...next,
  {
    ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts"],
  },
];

export default config;
