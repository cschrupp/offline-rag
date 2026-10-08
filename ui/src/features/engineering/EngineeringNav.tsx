import { NavLink } from "react-router-dom";

export function EngineeringNav() {
  return (
    <nav className="engineering-subnav" aria-label="Engineering">
      <NavLink to="/engineering/evaluation">Evaluation</NavLink>
      <NavLink to="/engineering/architecture">Architecture</NavLink>
    </nav>
  );
}
