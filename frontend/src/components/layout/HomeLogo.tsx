import { Link } from "react-router-dom";

export function HomeLogo() {
  return (
    <Link to="/" className="home-logo" aria-label="Paris Agent home">
      <span className="logo-mark">PA</span>
      <span>
        Paris
        <strong>Agent</strong>
      </span>
    </Link>
  );
}
