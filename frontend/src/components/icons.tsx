// Minimal stroke icons (24px grid, currentColor).
type P = { className?: string };
const base = (d: React.ReactNode, className = "h-5 w-5") => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
    {d}
  </svg>
);
export const IconSparkles = ({ className }: P) => base(<><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" /><path d="M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z" /></>, className);
export const IconImage = ({ className }: P) => base(<><rect x="3" y="4" width="18" height="16" rx="3" /><circle cx="9" cy="10" r="1.8" /><path d="M21 16l-5-5-9 9" /></>, className);
export const IconVideo = ({ className }: P) => base(<><rect x="3" y="5" width="13" height="14" rx="3" /><path d="M16 10l5-3v10l-5-3z" /></>, className);
export const IconBrush = ({ className }: P) => base(<><path d="M14.5 4.5l5 5L10 19H5v-5z" /><path d="M12.5 6.5l5 5" /></>, className);
export const IconGrid = ({ className }: P) => base(<><rect x="3.5" y="3.5" width="7" height="7" rx="2" /><rect x="13.5" y="3.5" width="7" height="7" rx="2" /><rect x="3.5" y="13.5" width="7" height="7" rx="2" /><rect x="13.5" y="13.5" width="7" height="7" rx="2" /></>, className);
export const IconUsers = ({ className }: P) => base(<><circle cx="9" cy="8" r="3.2" /><path d="M3 19c.8-3 3.2-4.5 6-4.5s5.2 1.5 6 4.5" /><path d="M16 5.2a3 3 0 010 5.6M18 14.8c1.5.6 2.5 1.9 3 4.2" /></>, className);
export const IconWand = ({ className }: P) => base(<><path d="M4 20L16 8" /><path d="M14 6l4 4" /><path d="M18 3v2M21 6h-2M20 9l1 1M12 3l1 1" /></>, className);
export const IconActivity = ({ className }: P) => base(<path d="M3 12h4l2.5-6 5 12 2.5-6H21" />, className);
export const IconCard = ({ className }: P) => base(<><rect x="3" y="5" width="18" height="14" rx="3" /><path d="M3 10h18M7 15h3" /></>, className);
export const IconShield = ({ className }: P) => base(<><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /><path d="M9 12l2 2 4-4" /></>, className);
export const IconMail = ({ className }: P) => base(<><rect x="3" y="5" width="18" height="14" rx="3" /><path d="M4 7l8 6 8-6" /></>, className);
export const IconArrowRight = ({ className }: P) => base(<path d="M5 12h14M13 6l6 6-6 6" />, className);
export const IconPlay = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className ?? "h-5 w-5"} aria-hidden><path d="M8 5.5v13a1 1 0 001.5.9l10.4-6.5a1 1 0 000-1.8L9.5 4.6A1 1 0 008 5.5z" /></svg>
);
export const IconCheck = ({ className }: P) => base(<path d="M5 12.5l4.5 4.5L19 7.5" />, className);
export const IconLogout = ({ className }: P) => base(<><path d="M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3" /><path d="M10 8l-4 4 4 4M6 12h10" /></>, className);
