export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { credentials: "include", ...options, headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...options.headers } });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || `Request failed (${response.status})`);
  if (typeof window !== "undefined" && ["/auth/login","/auth/logout","/auth/reset-password","/auth/change-password","/auth/account"].includes(path) && options.method && options.method !== "GET") window.dispatchEvent(new Event("humanloop-auth-change"));
  return payload as T;
}
export function post<T>(path: string, data?: unknown) { return api<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) }); }
export type User = { id: string; display_name: string; email: string; roles: string[]; email_verified: boolean; demo: boolean };
export type Worker = { id: string; user_id: string; display_name: string; headline: string; bio: string; city: string; category: string; skills: string[]; hourly_rate: number; currency: string; available: boolean; published: boolean; review_status: string; identity_verified: boolean; demo: boolean; completed_tasks: number; rating: number | null; review_count: number };
export type Task = { id: string; owner_id: string; assigned_worker_id: string | null; title: string; description: string; category: string; required_skills: string[]; city: string; budget: number; currency: string; expected_minutes: number; requirements: string; deadline?: string | null; visibility: string; status: string; payment_status: string; demo: boolean; created_at: string };
export type Page<T> = { items: T[]; total: number; page: number; limit: number };
export type Application = { id: string; task_id: string; worker_id: string; proposal: string; compensation: number; estimated_minutes: number; status: string };
export type Message = { id: string; sender_id: string; content: string; created_at: string };
export type Payment = { id: string; task_id: string; owner_id: string; amount: number; currency: string; provider: string; status: string };
export type Match = { worker: Worker; score: number; explanations: string[] };
export const categories = ["Retail checks", "Local research", "Photography", "Accessibility audits", "Translation"];
