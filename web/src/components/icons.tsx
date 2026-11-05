import type { ReactNode } from "react";

function Icon({ children, className = "size-4" }: { children: ReactNode; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {children}
    </svg>
  );
}

type Props = { className?: string };

export const SearchIcon = (p: Props) => <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Icon>;
export const RefreshIcon = (p: Props) => <Icon {...p}><path d="M20 11a8 8 0 0 0-14.3-4.3L4 8.5" /><path d="M4 4v4.5h4.5" /><path d="M4 13a8 8 0 0 0 14.3 4.3l1.7-1.8" /><path d="M20 20v-4.5h-4.5" /></Icon>;
export const ArrowIcon = (p: Props) => <Icon {...p}><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></Icon>;
export const SunIcon = (p: Props) => <Icon {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Icon>;
export const MoonIcon = (p: Props) => <Icon {...p}><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" /></Icon>;
export const NewsIcon = (p: Props) => <Icon {...p}><path d="M4 5h13v14a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2Z" /><path d="M17 9h3v10a2 2 0 0 1-2 2" /><path d="M8 9h5M8 13h5M8 17h3" /></Icon>;
export const StarIcon = (p: Props) => <Icon {...p}><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17.1 6.6 20l1-6.1L3.2 9.500l6.1-.9Z" /></Icon>;
export const CalendarIcon = (p: Props) => <Icon {...p}><rect x="4" y="5" width="16" height="16" rx="3" /><path d="M4 10h16M9 3v4M15 3v4" /></Icon>;
