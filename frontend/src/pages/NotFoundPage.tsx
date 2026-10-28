import { NavLink } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="not-found">
      <div className="not-found-code">404</div>
      <h1>Unknown destination</h1>
      <p>This route does not exist in the GreenScale workspace.</p>
      <NavLink className="button button-primary" to="/">
        Return to Command Center
      </NavLink>
    </div>
  );
}