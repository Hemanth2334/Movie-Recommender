import { useEffect, useRef, useState } from "react";

export const REGIONS = { US: "United States", GB: "United Kingdom", IN: "India", CA: "Canada", DE: "Germany", AU: "Australia" };

// Top bar: transparent over the hero banner, turns solid once you scroll.
export default function Navbar({ view, setView, region, setRegion, count, minRatings, user, onlyMine, setOnlyMine,
  onEditServices, onSignOut }) {
  const [solid, setSolid] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > 10);
    onScroll();
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const link = (id, label, disabled = false) => (
    <button className={`nav-link ${view === id ? "active" : ""}`} disabled={disabled} onClick={() => setView(id)}>
      {label}
    </button>
  );

  return (
    <header className={`navbar ${solid || view !== "home" ? "solid" : ""}`}>
      <div className="nav-left">
        <button className="logo" onClick={() => setView(count >= minRatings ? "home" : "rate")}>
          Cine<span>Match</span>
        </button>
        <nav>
          {link("home", "Home", count < minRatings)}
          {link("rate", "Rate movies")}
          {link("mylist", "My List")}
          {link("mine", `My ratings (${count})`)}
        </nav>
      </div>
      <div className="nav-right">
        <label className="switch" title="Only recommend movies on your services (or free)">
          <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} />
          <span className="switch-track"><span className="switch-thumb" /></span>
          <span className="switch-label">Only what I can stream</span>
        </label>
        <select className="region" value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Country">
          {Object.entries(REGIONS).map(([code, name]) => (
            <option key={code} value={code}>{name}</option>
          ))}
        </select>
        <div className="profile" ref={menuRef}>
          <button className="avatar" onClick={() => setMenuOpen((o) => !o)} aria-label="Profile menu" aria-expanded={menuOpen}>
            {(user?.name || "?").charAt(0).toUpperCase()}
          </button>
          {menuOpen && (
            <div className="menu">
              <div className="menu-head">
                <b>{user?.name}</b>
                <span className="muted">{user?.email}</span>
              </div>
              <button onClick={() => { setMenuOpen(false); onEditServices(); }}>
                My services <span className="muted">({user?.services?.length || 0} selected)</span>
              </button>
              <button onClick={() => { setMenuOpen(false); setView("mine"); }}>My ratings</button>
              <button onClick={() => { setMenuOpen(false); onSignOut(); }}>Sign out</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
