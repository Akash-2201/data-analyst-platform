import { useState } from "react";
import { supabase } from "./supabaseClient";
import DataStreamBackground from "./DataStreamBackground";

/**
 * AuthScreen — login / register screen using Supabase auth.
 * Toggles between sign-in and sign-up modes.
 * On success, calls onAuth() to let the parent know.
 */
export default function AuthScreen({ onAuth }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      if (mode === "register") {
        const { data, error: sbErr } = await supabase.auth.signUp({
          email,
          password,
        });
        if (sbErr) throw sbErr;
        if (data?.user?.identities?.length === 0) {
          setError("An account with this email already exists. Try logging in.");
        } else if (data?.session) {
          // Auto-confirmed (e.g. email confirmation disabled) → logged in
          onAuth(data.session);
        } else {
          setSuccessMsg("Check your email to confirm your account, then log in.");
        }
      } else {
        const { data, error: sbErr } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (sbErr) throw sbErr;
        onAuth(data.session);
      }
    } catch (err) {
      setError(err.message || "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-backdrop">
      <DataStreamBackground />
      <div className="auth-card">
        <div className="auth-logo">
          <img src="/datalyst-icon.svg" alt="Datalyst" className="auth-logo-icon" />
          <span className="auth-logo-text">Datalyst</span>
        </div>

        <h2 className="auth-title">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h2>
        <p className="auth-subtitle">
          {mode === "login"
            ? "Sign in to access your datasets and analyses"
            : "Get started with automated data profiling & cleaning"}
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-label" htmlFor="auth-email">
            Email
          </label>
          <input
            id="auth-email"
            className="auth-input"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
            autoComplete="email"
          />

          <label className="auth-label" htmlFor="auth-password">
            Password
          </label>
          <input
            id="auth-password"
            className="auth-input"
            type="password"
            placeholder={mode === "register" ? "Min 6 characters" : "Your password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />

          {error && <div className="auth-error">{error}</div>}
          {successMsg && <div className="auth-success">{successMsg}</div>}

          <button className="auth-submit" type="submit" disabled={loading}>
            {loading
              ? "Please wait…"
              : mode === "login"
              ? "Sign In"
              : "Create Account"}
          </button>
        </form>

        <div className="auth-footer">
          {mode === "login" ? (
            <>
              Don't have an account?{" "}
              <button
                className="auth-toggle"
                onClick={() => {
                  setMode("register");
                  setError(null);
                  setSuccessMsg(null);
                }}
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                className="auth-toggle"
                onClick={() => {
                  setMode("login");
                  setError(null);
                  setSuccessMsg(null);
                }}
              >
                Sign in
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
