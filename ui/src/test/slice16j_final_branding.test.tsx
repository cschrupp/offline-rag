import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AppRouter } from "../app/router";
import {
  AUTHOR_NAME,
  CONTACT_EMAIL,
  CONTACT_MAILTO,
  PRODUCT_DESCRIPTOR,
  PRODUCT_NAME,
  PRODUCT_VERSION,
  REPOSITORY_URL,
  WELCOME_SESSION_KEY,
} from "../product/identity";
import {
  createTestQueryClient,
  renderApp,
  seedFreshWelcomeSession,
  seedReturningWelcomeSession,
} from "./render";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ActiveOperationsBootstrap } from "../features/operations/ActiveOperationsBootstrap";

describe("S16-J final Seneca branding", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it("fresh root session shows Welcome outside AppShell", async () => {
    renderApp("/", { freshWelcomeSession: true });

    expect(await screen.findByTestId("seneca-welcome")).toBeInTheDocument();
    expect(screen.getByText("SENECA")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /GROUNDED KNOWLEDGE WORKSPACE/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Knowledge begins with evidence."),
    ).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "Open Workspace" });
    expect(cta).toHaveAttribute("href", "/workspaces");
    expect(
      screen.queryByRole("navigation", { name: "Primary" }),
    ).not.toBeInTheDocument();
    expect(sessionStorage.getItem(WELCOME_SESSION_KEY)).toBe("1");
  });

  it("returning session opens Overview with primary navigation", async () => {
    seedReturningWelcomeSession();
    renderApp("/");

    expect(
      await screen.findByRole("navigation", { name: "Primary" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("seneca-welcome")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
  });

  it("deep links bypass Welcome when session key is absent", async () => {
    const first = renderApp("/workspaces", { freshWelcomeSession: true });
    expect(
      await screen.findByRole("heading", { name: /Workspaces/i }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("seneca-welcome")).not.toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Primary" }),
    ).toBeInTheDocument();
    first.unmount();

    seedFreshWelcomeSession();
    renderApp("/gold-lab", { freshWelcomeSession: true });
    expect(
      await screen.findByRole("navigation", { name: "Primary" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("seneca-welcome")).not.toBeInTheDocument();
  });

  it("About dialog shows identity and Show welcome screen replays splash", async () => {
    const user = userEvent.setup();
    seedReturningWelcomeSession();
    renderApp("/");

    const about = await screen.findByRole("button", { name: "About" });
    expect(about).toHaveAttribute("aria-haspopup", "dialog");
    await user.click(about);

    const dialog = await screen.findByRole("dialog", { name: /About Seneca/i });
    expect(within(dialog).getByText(PRODUCT_NAME)).toBeInTheDocument();
    expect(within(dialog).getByText(PRODUCT_DESCRIPTOR)).toBeInTheDocument();
    expect(
      within(dialog).getByText(`Version ${PRODUCT_VERSION}`),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(`Created by ${AUTHOR_NAME}`),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(`© 2026 ${AUTHOR_NAME}`),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: CONTACT_EMAIL }),
    ).toHaveAttribute("href", CONTACT_MAILTO);
    expect(
      within(dialog).getByText(/Local-first · Evidence-grounded · Private by design/),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: "Contact" }),
    ).toHaveAttribute("href", CONTACT_MAILTO);
    expect(
      within(dialog).getByRole("link", { name: "Source repository" }),
    ).toHaveAttribute("href", REPOSITORY_URL);

    await user.click(
      within(dialog).getByRole("button", { name: "Show welcome screen" }),
    );
    expect(await screen.findByTestId("seneca-welcome")).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Primary" }),
    ).not.toBeInTheDocument();
  });

  it("Escape closes About and returns focus to About control", async () => {
    const user = userEvent.setup();
    seedReturningWelcomeSession();
    renderApp("/");

    const about = await screen.findByRole("button", { name: "About" });
    about.focus();
    await user.click(about);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(about).toHaveFocus();
  });

  it("keeps mobile nav open so About focus restores after Escape (F001)", async () => {
    const user = userEvent.setup();
    seedReturningWelcomeSession();
    renderApp("/");

    const menu = await screen.findByRole("button", { name: "Menu" });
    await user.click(menu);

    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(nav).toHaveClass("open");

    const about = within(nav).getByRole("button", { name: "About" });
    await user.click(about);

    expect(await screen.findByRole("dialog", { name: /About Seneca/i })).toBeInTheDocument();
    expect(nav).toHaveClass("open");

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(about).toHaveFocus();
    expect(nav).toHaveClass("open");
  });

  it("removes known rendered OfflineRAG product copy", async () => {
    seedReturningWelcomeSession();
    renderApp("/workspaces");
    expect(
      await screen.findByText(/this Seneca installation/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/OfflineRAG installation/i)).toBeNull();

    const { goldLabErrorMessage } = await import(
      "../features/goldLab/errors/goldLabErrors"
    );
    const { ApiError } = await import("../api/errors");
    const networkError = new ApiError({
      kind: "network",
      code: "network_error",
      message: "x",
      retryable: true,
    });
    expect(goldLabErrorMessage(networkError)).toMatch(/Could not reach Seneca/);
    expect(goldLabErrorMessage(networkError)).not.toMatch(/OfflineRAG/);
  });

  it("NotFound no longer claims Ask/Evidence/Training Mode unavailable", async () => {
    seedReturningWelcomeSession();
    renderApp("/this-route-does-not-exist");
    expect(
      await screen.findByText(/This Seneca page is not available/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Ask, Evidence, and Training Mode/i)).toBeNull();
  });

  it("explicit /welcome always renders Welcome", async () => {
    seedReturningWelcomeSession();
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/welcome"]}>
          <ActiveOperationsBootstrap />
          <AppRouter />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId("seneca-welcome")).toBeInTheDocument();
  });
});
