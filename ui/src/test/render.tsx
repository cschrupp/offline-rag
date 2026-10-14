import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { AppRouter } from "../app/router";
import { ActiveOperationsBootstrap } from "../features/operations/ActiveOperationsBootstrap";
import { WELCOME_SESSION_KEY } from "../product/identity";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

/** Default harness models a returning session so legacy tests keep Overview. */
export function seedReturningWelcomeSession(): void {
  sessionStorage.setItem(WELCOME_SESSION_KEY, "1");
}

export function seedFreshWelcomeSession(): void {
  sessionStorage.removeItem(WELCOME_SESSION_KEY);
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
  options?: Omit<RenderOptions, "wrapper"> & {
    /** When true, clears the welcome session key (16J fresh-session tests). */
    freshWelcomeSession?: boolean;
  },
) {
  const { freshWelcomeSession = false, ...renderOptions } = options ?? {};
  if (freshWelcomeSession) {
    seedFreshWelcomeSession();
  } else {
    seedReturningWelcomeSession();
  }
  const queryClient = createTestQueryClient();
  return {
    queryClient,
    ...render(<AppRouter />, {
      wrapper: ({ children }) => (
        <Providers queryClient={queryClient} initialPath={initialPath}>
          {children}
        </Providers>
      ),
      ...renderOptions,
    }),
  };
}

export function renderWithProviders(
  ui: ReactElement,
  {
    initialPath = "/",
    queryClient = createTestQueryClient(),
    freshWelcomeSession = false,
  }: {
    initialPath?: string;
    queryClient?: QueryClient;
    freshWelcomeSession?: boolean;
  } = {},
) {
  if (freshWelcomeSession) {
    seedFreshWelcomeSession();
  } else {
    seedReturningWelcomeSession();
  }
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
