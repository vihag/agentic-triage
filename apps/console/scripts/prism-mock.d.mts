export function startPrismMock(options?: { port?: number }): Promise<{
  baseUrl: string;
  specPath: string;
  stop: () => Promise<void>;
}>;
