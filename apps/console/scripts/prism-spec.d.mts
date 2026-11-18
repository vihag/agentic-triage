export function buildPrismSpec(): unknown;
export function loadPositiveExamples(): Array<{
  file: string;
  schema: string;
  variant: string;
  value: unknown;
}>;
export function writePrismSpec(dest?: string): string;
