import { NavLink } from "react-router-dom";

export function EngineeringNav() {
  return (
    <nav className="engineering-subnav" aria-label="Engineering">
      <NavLink to="/engineering/summary">Summary</NavLink>
      <NavLink to="/engineering/architecture">Architecture</NavLink>
      <NavLink to="/engineering/evidence">Evidence</NavLink>
    </nav>
  );
}
