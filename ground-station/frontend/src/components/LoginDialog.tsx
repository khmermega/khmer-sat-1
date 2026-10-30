import { useState } from "react";
import { api, setToken } from "../api";
import { Button, inputCls } from "./Panel";

export function LoginDialog({ onClose, onSuccess }: { onClose: () => void; onSuccess: (role: string) => void }) {
  const [token, setTok] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError("");
    setToken(token.trim());
    try {
      const who = await api.whoami();
      onSuccess(who.role);
    } catch (e) {
      setToken("");
      setError(e instanceof Error ? e.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/80 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <form
        className="w-full max-w-sm rounded-xl border border-line-2 bg-panel p-5 shadow-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <h2 className="text-sm font-semibold tracking-wide text-ink">Operator sign-in</h2>
        <p className="mt-1 text-xs leading-relaxed text-ink-3">
          Paste the <code className="text-ink-2">OPERATOR_TOKEN</code> or <code className="text-ink-2">ADMIN_TOKEN</code> from your <code className="text-ink-2">.env</code>. The token is kept only in
          this browser tab's session storage.
        </p>
        <input autoFocus type="password" className={`${inputCls} mt-4`} placeholder="bearer token" value={token} onChange={(e) => setTok(e.target.value)} aria-label="Operator token" />
        {error && <p className="mt-2 text-xs text-crit">{error}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!token.trim() || busy}>
            {busy ? "Checking…" : "Sign in"}
          </Button>
        </div>
      </form>
    </div>
  );
}
