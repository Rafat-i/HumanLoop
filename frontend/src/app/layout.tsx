import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { Header, Footer } from "@/components/shell";
import "./globals.css";
export const metadata: Metadata = { title: { default: "HumanLoop — When AI needs human hands.", template: "%s · HumanLoop" }, description: "A human-first marketplace for the work beyond the screen. Local demonstration, with accountable agent tools." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" suppressHydrationWarning><body><script dangerouslySetInnerHTML={{__html:"try{const t=localStorage.getItem('humanloop-theme');document.documentElement.classList.toggle('dark',t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches))}catch{}"}}/><Providers><a className="skip-link" href="#main">Skip to content</a><Header /><main id="main">{children}</main><Footer /></Providers></body></html>; }
