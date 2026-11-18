# ADR-0004: React + Vite + TypeScript for the Analyst Console, typed from OpenAPI

* Status: Accepted · Date: 2026-11-18 · Owner: Architect, Frontend engineer

## Decision
React 18 + Vite + TypeScript, TanStack Query, a small component kit (shadcn/ui + Tailwind). Types and client are **generated from `contracts/openapi.yaml`** (openapi-typescript + openapi-fetch). During M1-M3 the console runs against a **Prism mock** serving `contracts/examples`.

## Alternatives
Next.js (SSR not needed for an internal console); Streamlit (fast but weak for an approvals workflow and a credible "product" demo).

## Consequences
Frontend starts on day 1 without the backend; any contract drift is a compile error.
