"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth";
import { config } from "@/lib/config";

function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, signInWithGoogle, signInWithEmail } = useAuth();
  const [create, setCreate] = useState(params.get("mode") === "signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) router.replace("/studio");
  }, [user, router]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  const dev = config.authMode === "dev";

  return (
    <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-white/[0.03] p-8">
      <h1 className="text-xl font-semibold">{create ? "Create your account" : "Welcome back"}</h1>
      <p className="mt-1 text-sm text-zinc-400">
        {create ? "New accounts get free credits to start." : "Sign in to your studio."}
      </p>

      {!dev && (
        <button
          disabled={busy}
          onClick={() => run(signInWithGoogle)}
          className="mt-6 w-full rounded-lg bg-white py-2.5 font-medium text-black hover:bg-zinc-200 disabled:opacity-50"
        >
          Continue with Google
        </button>
      )}

      <form
        className="mt-6 space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          run(() => signInWithEmail(email, password, create));
        }}
      >
        <input
          type="email"
          required
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 outline-none focus:border-violet-400"
        />
        {!dev && (
          <input
            type="password"
            required
            minLength={8}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 outline-none focus:border-violet-400"
          />
        )}
        <button
          disabled={busy}
          className="w-full rounded-lg border border-white/15 py-2.5 hover:bg-white/5 disabled:opacity-50"
        >
          {dev ? "Sign in (dev mode)" : create ? "Create account with email" : "Sign in with email"}
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <button onClick={() => setCreate(!create)} className="mt-6 text-sm text-zinc-400 hover:text-white">
        {create ? "Already have an account? Sign in" : "New here? Create an account"}
      </button>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 px-4">
      <Logo />
      <Suspense>
        <LoginForm />
      </Suspense>
    </div>
  );
}
