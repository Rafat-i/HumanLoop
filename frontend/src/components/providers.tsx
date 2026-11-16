"use client";
import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@/lib/query";
import { Toaster } from "@/components/toast";
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 15000 } } }));
  useEffect(() => { const reset = () => { client.clear(); void client.invalidateQueries(); }; window.addEventListener("humanloop-auth-change", reset); return () => window.removeEventListener("humanloop-auth-change", reset); }, [client]);
  return <QueryClientProvider client={client}>{children}<Toaster richColors closeButton /></QueryClientProvider>;
}
