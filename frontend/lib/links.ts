/**
 * Every URL the site points at, written once.
 *
 * They were declared per component, and the predictable thing happened: the footer linked
 * `/in/jose-luis-romo-dev-data` while the methodology page linked `/in/jose-luis-romo`,
 * which is not an account. Two constants for one address is one too many, and nothing in a
 * static export fails when they drift — a wrong link renders perfectly.
 *
 * The API base URL is **not** here. That one is configuration rather than a link: it is
 * read from `NEXT_PUBLIC_API_BASE_URL` in `lib/api.ts` so a deployment can point the form
 * at another service, and duplicating it as a constant would defeat that.
 */

/** The deployed site, which `metadata` resolves relative URLs against. */
export const SITE_URL = "https://autovalor-web.onrender.com";

export const REPO_URL = "https://github.com/JoseRomo16/AutoValorCo";

/** The orphan branch the weekly captures live on; see ADR 0004. */
export const DATA_BRANCH_URL = `${REPO_URL}/tree/data`;

export const DECISIONS_URL = `${REPO_URL}/tree/main/docs/adr`;

export const STATUS_URL = `${REPO_URL}/blob/main/docs/STATUS.md`;

/** The live service's own documentation, which is the F4 deliverable readers check. */
export const API_DOCS_URL = "https://autovalor-api.onrender.com/docs";

export const MODEL_INFO_URL = "https://autovalor-api.onrender.com/model-info";

/** The author. The one that was wrong in two places. */
export const LINKEDIN_URL = "https://www.linkedin.com/in/jose-luis-romo-dev-data";
