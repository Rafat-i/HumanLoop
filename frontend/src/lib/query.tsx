"use client";
// Small fetch cache for this preview. Replace with TanStack Query when broadening cache policies.
import { createContext,useContext,useEffect,useState,useSyncExternalStore } from "react";
type State<T> = {isPending:true;error:null;data:undefined}|{isPending:false;error:Error;data:undefined}|{isPending:false;error:null;data:T};
type Entry = {state:State<unknown>;listeners:Set<()=>void>;fetcher?:()=>Promise<unknown>;running:boolean;loadedAt:number};
export class QueryClient {
 private entries=new Map<string,Entry>();
 private generation=0;
 clear(){this.generation++;for(const e of this.entries.values()){e.state={isPending:true,error:null,data:undefined};e.loadedAt=0;e.running=false;e.listeners.forEach(l=>l());}}
 constructor(_options?:unknown){void _options;}
 entry(key:string){let entry=this.entries.get(key);if(!entry){entry={state:{isPending:true,error:null,data:undefined},listeners:new Set(),running:false,loadedAt:0};this.entries.set(key,entry);}return entry;}
 subscribe(key:string,listener:()=>void){const e=this.entry(key);e.listeners.add(listener);return()=>{e.listeners.delete(listener);};}
 snapshot(key:string){return this.entry(key).state;}
 configure(key:string,fetcher:(()=>Promise<unknown>)|undefined){const e=this.entry(key);e.fetcher=fetcher;if(fetcher&&Date.now()-e.loadedAt>15000)void this.fetch(key);}
 async fetch(key:string){const e=this.entry(key);if(e.running||!e.fetcher)return;e.running=true;const generation=this.generation;try{const data=await e.fetcher();if(generation!==this.generation)return;e.state={isPending:false,error:null,data};}catch(error){if(generation!==this.generation)return;e.state={isPending:false,error:error instanceof Error?error:new Error("Request failed"),data:undefined};}finally{if(generation===this.generation){e.running=false;e.loadedAt=Date.now();e.listeners.forEach(l=>l());}}}
 async invalidateQueries(filter?:{queryKey:unknown[]}){const prefix=filter?JSON.stringify(filter.queryKey).slice(0,-1):null;await Promise.all([...this.entries.keys()].filter(k=>!prefix||k.startsWith(prefix)).map(k=>{const e=this.entry(k);e.loadedAt=0;return e.listeners.size?this.fetch(k):Promise.resolve();}));}
}
const Context=createContext<QueryClient|null>(null);
export function QueryClientProvider({client,children}:{client:QueryClient;children:React.ReactNode}){return <Context.Provider value={client}>{children}</Context.Provider>;}
export function useQueryClient(){const client=useContext(Context);if(!client)throw new Error("Query provider missing");return client;}
export function useQuery<T>({queryKey,queryFn,enabled=true,refetchInterval}:{queryKey:unknown[];queryFn:()=>Promise<T>;enabled?:boolean;retry?:boolean;refetchInterval?:number}){
 const client=useQueryClient();const key=JSON.stringify(queryKey);
 const state=useSyncExternalStore(listener=>client.subscribe(key,listener),()=>client.snapshot(key),()=>client.snapshot(key)) as State<T>;
 useEffect(()=>{client.configure(key,enabled?queryFn:undefined);if(enabled&&refetchInterval){const interval=setInterval(()=>void client.fetch(key),refetchInterval);return()=>clearInterval(interval);}},[client,key,enabled,refetchInterval,queryFn]);
 return state;
}
export function useMutation<T,V=void>({mutationFn,onSuccess,onError}:{mutationFn:(value:V)=>Promise<T>;onSuccess?:(value:T)=>unknown;onError?:(error:Error)=>unknown}){
 const [isPending,setPending]=useState(false);
 return {isPending,mutate:(value?:V,overrides?:{onSuccess?:(value:T)=>unknown})=>{setPending(true);void mutationFn(value as V).then(async result=>{await onSuccess?.(result);await overrides?.onSuccess?.(result);}).catch(error=>onError?.(error instanceof Error?error:new Error("Request failed"))).finally(()=>setPending(false));}};
}
