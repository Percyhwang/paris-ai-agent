import { Link } from "react-router-dom";

export function HomeLogo() {
  return (
    <Link to="/" className="home-logo" aria-label="ViaParis home">
      <img className="brand-logo-image" src={`${import.meta.env.BASE_URL}images/viaparis-logo.svg`} alt="" aria-hidden="true" />
    </Link>
  );
}
