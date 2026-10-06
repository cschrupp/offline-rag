import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="app-header">
        <div className="app-header-inner">
          <NavLink to="/" className="brand" onClick={() => setNavOpen(false)}>
            <span className="brand-mark" aria-hidden="true">
              OR
            </span>
            <span>OfflineRAG</span>
          </NavLink>
          <button
            type="button"
            className="nav-toggle"
            aria-expanded={navOpen}
            aria-controls="primary-navigation"
            onClick={() => setNavOpen((open) => !open)}
          >
            Menu
          </button>
          <nav
            id="primary-navigation"
            className={`primary-nav${navOpen ? " open" : ""}`}
            aria-label="Primary"
          >
            <NavLink to="/" end onClick={() => setNavOpen(false)}>
              Overview
            </NavLink>
            <NavLink to="/workspaces" onClick={() => setNavOpen(false)}>
              Workspaces
            </NavLink>
          </nav>
        </div>
      </header>
      <main id="main-content" className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
