import { useEffect, useState } from "react";
import { api } from "../api.js";

// "Which services do you pay for?" Shown after sign-up and from the profile menu.
export default function ServicesPicker({ initial = [], firstTime = false, onDone, onCancel }) {
  const [all, setAll] = useState([]);
  const [chosen, setChosen] = useState(new Set(initial));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.services().then(setAll);
  }, []);

  const toggle = (key) =>
    setChosen((s) => {
      const next = new Set(s);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  async function save() {
    setBusy(true);
    const user = await api.setServices([...chosen]);
    setBusy(false);
    onDone(user);
  }

  return (
    <div className="modal-overlay" onClick={firstTime ? undefined : onCancel}>
      <div className="services-card" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="My services">
        <h2>{firstTime ? "Which services do you have?" : "My services"}</h2>
        <p className="muted">
          Pick the streaming services you pay for. Turn on <b>Only what I can stream</b> and CineMatch will only recommend
          movies on these (plus anything free).
        </p>
        <div className="services-grid">
          {all.map((s) => (
            <button key={s.key} className={`service-tile ${chosen.has(s.key) ? "on" : ""}`} onClick={() => toggle(s.key)} aria-pressed={chosen.has(s.key)}>
              <span className="service-check">{chosen.has(s.key) ? "✓" : ""}</span>
              {s.name}
            </button>
          ))}
        </div>
        <div className="services-actions">
          {!firstTime && <button className="btn btn-glass" onClick={onCancel}>Cancel</button>}
          {firstTime && <button className="btn btn-glass" onClick={() => onDone(null)}>Skip for now</button>}
          <button className="btn btn-accent" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}
