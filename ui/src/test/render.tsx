import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { AppRouter } from "../app/router";
import { ActiveOperationsBootstrap } from "../features/operations/ActiveOperationsBootstrap";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function Providers({
  children,
  queryClient,
  initialPath,
}: {
  children: ReactNode;
  queryClient: QueryClient;
  initialPath: string;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <ActiveOperationsBootstrap />
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  );
}

export function renderApp(
  initialPath = "/",
  options?: Omit<RenderOptions, "wrapper">,
) {
  const queryClient = createTestQueryClient();
  return {
    queryClient,
    ...render(<AppRouter />, {
      wrapper: ({ children }) => (
        <Providers queryClient={queryClient} initialPath={initialPath}>
          {children}
        </Providers>
      ),
      ...options,
    }),
  };
}

export function renderWithProviders(
  ui: ReactElement,
  {
    initialPath = "/",
    queryClient = createTestQueryClient(),
  }: { initialPath?: string; queryClient?: QueryClient } = {},
) {
  return {
    queryClient,
    ...render(ui, {
      wrapper: ({ children }) => (
        <Providers queryClient={queryClient} initialPath={initialPath}>
          {children}
        </Providers>
      ),
    }),
  };
}
