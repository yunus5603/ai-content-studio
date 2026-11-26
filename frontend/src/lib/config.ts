export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  // "dev" signs in with any email (backend must run AUTH_MODE=dev). "firebase" uses Identity Platform.
  authMode: (process.env.NEXT_PUBLIC_AUTH_MODE ?? "dev") as "dev" | "firebase",
  firebase: {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
  },
};
