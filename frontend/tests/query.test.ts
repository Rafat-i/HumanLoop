import { expect, it } from "vitest";
import { QueryClient } from "@/lib/query";
it("does not restore old private data after an account change", async () => {
 const client = new QueryClient(); let resolve: (value:unknown)=>void = ()=>{};
 client.configure("private",()=>new Promise(r=>{resolve=r;}));
 client.clear(); resolve({secret:"previous-account-data"});
 await new Promise(r=>setTimeout(r,0));
 expect(client.snapshot("private").data).toBeUndefined();
});
