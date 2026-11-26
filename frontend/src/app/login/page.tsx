"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { AutoVideo } from "@/components/reveal";
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
    <div className="w-full max-w-sm animate-fade-up">
      <h1 className="text-3xl font-semibold tracking-tight">{create ? "Create your account" : "Welcome back"}</h1>
      <p className="mt-1 text-sm text-muted">
        {create ? "New accounts get free credits to start." : "Sign in to your studio."}
      </p>

      {!dev && (
        <button
          disabled={busy}
          onClick={() => run(signInWithGoogle)}
          className="btn btn-secondary mt-8 w-full py-2.5"
        >
          Continue with Google
        </button>
      )}

      <form
        className={`${dev ? "mt-8" : "mt-4"} space-y-3`}
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
          className="input py-2.5"
        />
        {!dev && (
          <input
            type="password"
            required
            minLength={8}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input py-2.5"
          />
        )}
        <button
          disabled={busy}
          className="btn btn-primary w-full py-2.5"
        >
          {dev ? "Sign in (dev mode)" : create ? "Create account with email" : "Sign in with email"}
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}

      <button onClick={() => setCreate(!create)} className="mt-6 text-sm text-muted hover:text-ink">
        {create ? "Already have an account? Sign in" : "New here? Create an account"}
      </button>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col px-6 py-6 sm:px-10">
        <Logo />
        <div className="flex flex-1 items-center justify-center py-12">
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
        <p className="text-xs text-subtle">New accounts start with free credits. No card needed to try it.</p>
      </div>
      <div className="relative hidden overflow-hidden p-3 lg:block">
        <div className="relative h-full overflow-hidden rounded-[1.75rem]">
          <AutoVideo src="/samples/orbs-loop.mp4" poster="/samples/orbs-loop.jpg" className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/65 via-black/25 to-transparent p-10 pt-40 text-white">
            <p className="max-w-md text-2xl font-medium leading-snug tracking-tight">
              “Every top image and video model, one prompt box, and a gallery that keeps everything.”
            </p>
            <div className="mt-6 flex flex-wrap gap-2 text-xs">
              {["GPT Image", "Gemini", "Veo 3.1", "Copilot"].map((m) => (
                <span key={m} className="rounded-full border border-white/30 bg-white/15 px-3 py-1 backdrop-blur">{m}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
