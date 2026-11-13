import { useState } from "react";
import { api, setToken } from "../api.js";

// Sign in / create account. On success calls onAuthed(user, isNewAccount).
export default function AuthPage({ onAuthed }) {
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isSignup = mode === "signup";

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (isSignup && password.length < 6) return setError("Password must be at least 6 characters.");
    setBusy(true);
    try {
      // ratings made in this browser before accounts existed move into the new account
      const legacy = localStorage.getItem("userId");
      const res = isSignup ? await api.signup(name, email, password, legacy) : await api.login(email, password);
      if (isSignup) localStorage.removeItem("userId");
      setToken(res.token);
      onAuthed(res.user, isSignup);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth-bg" />
      <header className="auth-top">
        <span className="logo">Cine<span>Match</span></span>
      </header>
      <main className="auth-main">
        <div className="auth-pitch">
          <h1>Movies picked for you, and where to watch them.</h1>
          <p>Rate a few films you know. CineMatch learns your taste from people like you and shows what's on your streaming services.</p>
        </div>
        <form className="auth-card" onSubmit={submit}>
          <h2>{isSignup ? "Create your account" : "Sign in"}</h2>
          {isSignup && (
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={40} autoComplete="name" />
            </label>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={isSignup ? 6 : 1}
              autoComplete={isSignup ? "new-password" : "current-password"}
            />
          </label>
          {isSignup && <p className="hint">At least 6 characters.</p>}
          {error && <p className="auth-error">{error}</p>}
          <button className="btn btn-accent auth-submit" disabled={busy}>
            {busy ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
          </button>
          <p className="auth-switch">
            {isSignup ? "Already have an account? " : "New to CineMatch? "}
            <button type="button" className="link-btn" onClick={() => { setMode(isSignup ? "signin" : "signup"); setError(""); }}>
              {isSignup ? "Sign in" : "Create an account"}
            </button>
          </p>
        </form>
      </main>
    </div>
  );
}
