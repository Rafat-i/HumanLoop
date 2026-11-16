import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...values: ClassValue[]) { return twMerge(clsx(values)); }
export function money(amount: number, currency = "CAD") { return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(amount / 100); }
export function humanize(value: string) { return value.toLowerCase().replaceAll("_", " "); }
