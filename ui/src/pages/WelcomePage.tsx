import { useEffect } from "react";
import { Button } from "../components/Button";
import {
  PRODUCT_DESCRIPTOR,
  PRODUCT_NAME,
  WELCOME_SESSION_KEY,
} from "../product/identity";

export function WelcomePage() {
  useEffect(() => {
    try {
      sessionStorage.setItem(WELCOME_SESSION_KEY, "1");
    } catch {
      // sessionStorage may be unavailable; welcome still renders.
    }
  }, []);

  return (
    <div className="welcome-screen" data-testid="seneca-welcome">
      <a className="skip-link" href="#welcome-main">
        Skip to content
      </a>
      <div className="welcome-layout">
        <main id="welcome-main" className="welcome-copy">
          <p className="welcome-kicker">{PRODUCT_NAME.toUpperCase()}</p>
          <h1 className="welcome-title">{PRODUCT_DESCRIPTOR.toUpperCase()}</h1>
          <p className="welcome-tagline">Knowledge begins with evidence.</p>
          <p className="welcome-body">
            Bring your documents together, ask questions, and trace answers back
            to their sources.
          </p>
          <p className="welcome-cta">
            <Button to="/workspaces" variant="primary">
              Open Workspace
            </Button>
          </p>
          <ul className="welcome-pillars">
            <li>Local-first</li>
            <li>Evidence-grounded</li>
            <li>Private by design</li>
          </ul>
        </main>
        <aside className="welcome-art" aria-hidden="true">
          <picture>
            <source
              media="(max-width: 767px)"
              srcSet="/brand/seneca/seneca-splash-mobile-4x5.webp"
            />
            <source
              media="(min-width: 1600px)"
              srcSet="/brand/seneca/seneca-splash-background-1600.webp"
            />
            <source
              media="(min-width: 1280px)"
              srcSet="/brand/seneca/seneca-splash-background-1280.webp"
            />
            <img
              className="welcome-art-image"
              src="/brand/seneca/seneca-splash-background-960.webp"
              alt=""
              width={960}
              height={540}
              decoding="async"
            />
          </picture>
        </aside>
      </div>
    </div>
  );
}
