"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
export type Field = { name: string; label: string; type?: string; options?: string[]; defaultValue?: string; required?: boolean; min?: number; max?: number; minLength?: number; maxLength?: number };
const strings = z.record(z.string(),z.string());
export function SimpleForm({ fields, submit, button = "Save", defaults = {} }: { fields: Field[]; submit: (values: Record<string,string>) => Promise<unknown>; button?: string; defaults?: Record<string,string> }) {
 const form = useForm<Record<string,string>>({ resolver: zodResolver(strings), defaultValues: Object.fromEntries(fields.map(f=>[f.name,defaults[f.name]??f.defaultValue??""])) });
 const [error,setError]=useState(""); const [success,setSuccess]=useState(false);
 return <form className="form" onSubmit={form.handleSubmit(async values=>{setError("");setSuccess(false);try{await submit(values);setSuccess(true);}catch(e){setError(e instanceof Error?e.message:"Unable to save");}})}>{fields.map(f=><label className="field" key={f.name}><span>{f.label}</span>{f.options?<select {...form.register(f.name)} required={f.required!==false}>{f.options.map(o=><option key={o} value={o}>{o}</option>)}</select>:f.type==="textarea"?<textarea {...form.register(f.name)} required={f.required!==false} minLength={f.minLength} maxLength={f.maxLength??8000}/>:<input {...form.register(f.name)} type={f.type??"text"} required={f.required!==false} min={f.min} max={f.max} minLength={f.minLength} maxLength={f.maxLength??255} autoComplete={f.type==="password"?"new-password":undefined}/>}</label>)}{error&&<p className="form-error" role="alert">{error}</p>}{success&&<p role="status" style={{color:"var(--accent)",fontSize:12}}>Saved successfully.</p>}<Button disabled={form.formState.isSubmitting}>{form.formState.isSubmitting?"Saving…":button}</Button></form>;
}
