"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { config } from "./config";

type SessionUser = { email: string; displayName: string | null; emailVerified: boolean };

type AuthState = {
  user: SessionUser | null;
  loading: boolean;
  /** Headers that authenticate an API request, or null when signed out. */
  authHeaders: () => Promise<Record<string, string> | null>;
  signInWithGoogle: () => Promise<void>;
  signInWithEmail: (email: string, password: string, create: boolean) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);
const DEV_KEY = "studio.devUser";

async function firebaseAuth() {
  const { initializeApp, getApps } = await import("firebase/app");
  const auth = await import("firebase/auth");
  const app = getApps()[0] ?? initializeApp(config.firebase);
  return { auth, instance: auth.getAuth(app) };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (config.authMode === "dev") {
      let email: string | null = null;
      try {
        email = localStorage.getItem(DEV_KEY);
      } catch {}
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time read of browser storage
      setUser(email ? { email, displayName: email.split("@")[0], emailVerified: true } : null);
      setLoading(false);
      return;
    }
    let unsubscribe = () => {};
    firebaseAuth().then(({ auth, instance }) => {
      unsubscribe = auth.onIdTokenChanged(instance, (u) => {
        setUser(u ? { email: u.email ?? "", displayName: u.displayName, emailVerified: u.emailVerified } : null);
        setLoading(false);
      });
    });
    return () => unsubscribe();
  }, []);

  const authHeaders = useCallback(async (): Promise<Record<string, string> | null> => {
    if (config.authMode === "dev") {
      return user ? { "X-Dev-User": user.email } : null;
    }
    const { instance } = await firebaseAuth();
    const token = await instance.currentUser?.getIdToken();
    return token ? { Authorization: `Bearer ${token}` } : null;
  }, [user]);

  const signInWithGoogle = useCallback(async () => {
    const { auth, instance } = await firebaseAuth();
    await auth.signInWithPopup(instance, new auth.GoogleAuthProvider());
  }, []);

  const signInWithEmail = useCallback(async (email: string, password: string, create: boolean) => {
    if (config.authMode === "dev") {
      const normalized = email.trim().toLowerCase();
      try {
        localStorage.setItem(DEV_KEY, normalized);
      } catch {}
      setUser({ email: normalized, displayName: normalized.split("@")[0], emailVerified: true });
      return;
    }
    const { auth, instance } = await firebaseAuth();
    if (create) {
      const cred = await auth.createUserWithEmailAndPassword(instance, email, password);
      await auth.sendEmailVerification(cred.user);
    } else {
      await auth.signInWithEmailAndPassword(instance, email, password);
    }
  }, []);

  const signOut = useCallback(async () => {
    if (config.authMode === "dev") {
      try {
        localStorage.removeItem(DEV_KEY);
      } catch {}
      setUser(null);
      return;
    }
    const { auth, instance } = await firebaseAuth();
    await auth.signOut(instance);
  }, []);

  const value = useMemo(
    () => ({ user, loading, authHeaders, signInWithGoogle, signInWithEmail, signOut }),
    [user, loading, authHeaders, signInWithGoogle, signInWithEmail, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
