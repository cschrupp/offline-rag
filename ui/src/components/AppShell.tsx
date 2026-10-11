import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Settings } from "lucide-react";

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
              <img src="/favicon.svg" alt="" width={28} height={28} />
            </span>
            <span className="brand-text">
              <span className="brand-name">Seneca</span>
              <span className="brand-descriptor">Grounded knowledge workspace</span>
            </span>
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
            <NavLink to="/gold-lab" onClick={() => setNavOpen(false)}>
              Gold Lab
            </NavLink>
            <NavLink to="/engineering" onClick={() => setNavOpen(false)}>
              Engineering
            </NavLink>
            <NavLink
              to="/settings"
              className="nav-settings"
              onClick={() => setNavOpen(false)}
              aria-label="Settings"
            >
              <Settings size={18} aria-hidden="true" />
              <span>Settings</span>
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
