"use client";
import {useEffect,useState} from "react";
type Notice={id:number;text:string;kind:"success"|"error"};
const listeners=new Set<(notice:Notice)=>void>();let sequence=0;
function send(text:string,kind:Notice["kind"]){const notice={id:++sequence,text,kind};listeners.forEach(l=>l(notice));}
export const toast={success:(text:string)=>send(text,"success"),error:(text:string)=>send(text,"error")};
export function Toaster(_props:{richColors?:boolean;closeButton?:boolean}){void _props;const [items,setItems]=useState<Notice[]>([]);useEffect(()=>{const listener=(n:Notice)=>setItems(old=>[...old.slice(-3),n]);listeners.add(listener);return()=>{listeners.delete(listener);};},[]);return <div className="toast-stack" aria-live="polite">{items.map(item=><div className={`toast ${item.kind}`} role={item.kind==="error"?"alert":"status"} key={item.id}><span>{item.text}</span><button onClick={()=>setItems(old=>old.filter(n=>n.id!==item.id))} aria-label="Dismiss notification">×</button></div>)}</div>;}
