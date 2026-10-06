import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        // Never auto-retry mutations: idempotency keys must stay intentional.
        retry: false,
      },
    },
  });
}
