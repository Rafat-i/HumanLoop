"use client";
import Link from "next/link";
import { ArrowRight, ArrowUpRight, Check, Code2, LockKeyhole, Camera, FileText } from "lucide-react";
import { useQuery } from "@/lib/query";
import { api, type Worker } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading, WorkerCard } from "@/components/common";

export default function Home() {
  const workers = useQuery({ queryKey: ["showcase-workers"], queryFn: () => api<Worker[]>("/workers/showcase") });
  return <div className="container editorial-home">
    <section className="editorial-hero">
      <div className="hero-copy">
        <h1>When AI needs<br/><span>human hands.</span></h1>
        <p>Your agent can search the web. It cannot check the shelf. Request an in-store product check, choose a worker and review the evidence they bring back.</p>
        <div className="actions"><Button asChild><Link href="/marketplace">Find a human <ArrowUpRight size={17}/></Link></Button><Button asChild variant="outline"><Link href="/developers/docs">Build an integration</Link></Button></div>
        <p className="hero-footnote">Local development preview. No public bookings or real payments.</p>
      </div>
      <figure className="product-preview">
        <figcaption><span>Task workspace</span><span>Illustrative example</span></figcaption>
        <div className="preview-body">
          <div className="preview-source"><Code2 size={16}/><span>Inventory assistant / scoped API key</span></div>
          <div className="preview-title"><h2>Online says available.<br/>Is it on the shelf?</h2><span className="tag">Awaiting owner review</span></div>
          <p className="preview-brief">Verify a black, 750 ml insulated bottle at a public retail location. Match the model, colour and size. Do not purchase anything.</p>
          <dl className="preview-facts"><div><dt>Location</dt><dd>Toronto retail store</dd></div><div><dt>Budget</dt><dd>$30 CAD / fixed</dd></div><div><dt>Scope</dt><dd>One product check</dd></div></dl>
          <div className="preview-evidence"><Camera size={18}/><div><strong>Permitted shelf photo + short report</strong><p>Record product details and availability. No faces, receipts or private areas. If photography is prohibited, report that limitation.</p></div></div>
          <ol className="handoff-list">
            <li><Check size={15}/><span>Agent drafts the scope</span><small>Prepared</small></li>
            <li><span className="step-dot"/><span>Owner approves and selects a worker</span><small>Pending</small></li>
            <li><span className="step-dot"/><span>Worker accepts, then visits</span><small>Not started</small></li>
            <li><FileText size={15}/><span>Evidence submitted; owner reviews completion</span><small>Pending</small></li>
          </ol>
          <p className="preview-caption"><LockKeyhole size={13}/> Private messages and evidence. No work is booked here.</p>
        </div>
      </figure>
    </section>
    <div className="principle-bar"><span>Agents propose.</span><span>Owners approve.</span><span>Workers choose.</span></div>
    <section className="editorial-section mechanism">
      <div><h2>From a digital request<br/>to a physical observation.</h2><p>An inventory page is a claim. A worker can check the actual product, document what they see and explain what they could not verify.</p></div>
      <div className="editorial-steps">{[
        ["01", "Describe the outcome", "Set the scope, location and budget. Draft it yourself or let your agent propose it through the API."],
        ["02", "Make the human decisions", "Review candidates and applications. You select a worker; they explicitly accept before starting."],
        ["03", "Review what comes back", "Exchange private messages, inspect submitted evidence and approve completion. Payments stay simulated in this preview."]
      ].map(([n,title,text])=><article key={n}><span className="sequence">{n}</span><div><h3>{title}</h3><p>{text}</p></div></article>)}</div>
    </section>
    <section className="editorial-section">
      <div className="section-heading"><div><h2>Different tasks. Specific people.</h2><p>Retail observation, permitted photography and accessibility research. Published profiles below are loaded from the marketplace. Demo profiles are fictional.</p></div><Link className="text-link" href="/marketplace">Explore the marketplace <ArrowRight size={16}/></Link></div>
      <div className="grid-3">{workers.isPending?<Loading/>:workers.error?<ErrorState error={workers.error}/>:workers.data.length?workers.data.map(w=><WorkerCard key={w.id} worker={w}/>):<Empty title="No showcase profiles yet" text="Load the fictional demo profiles to explore the marketplace, or publish a reviewed worker profile."/>}</div>
    </section>
    <section className="editorial-section developer-feature">
      <div><h2>A small API.<br/>A deliberate boundary.</h2><p>Discover workers, create drafts and retrieve results with account-owned credentials. Publication, assignment and payments stay outside the agent toolset.</p><Link className="text-link" href="/developers/docs">Read the API & MCP documentation <ArrowRight size={16}/></Link></div>
      <div className="api-example"><div className="api-example-head"><span>REST / local MCP</span><span>Draft only</span></div><pre><code>{`POST /api/v1/agent/tasks/drafts
Authorization: Bearer <scoped-key>
Idempotency-Key: <unique-request-id>

{
  "title": "Verify a product in store",
  "description": "Check the specified bottle on the shelf. Submit permitted photo evidence and a short report. No purchase.",
  "category": "Retail checks",
  "city": "Toronto",
  "budget": 3000,
  "currency": "CAD"
}`}</code></pre><p>Example request. 3000 minor units = $30.00 CAD.</p></div>
    </section>
    <section className="editorial-section worker-invitation"><h2>Your skills.<br/>Your decision.</h2><div><p>Publish only what you choose to share. Find a clear brief, propose your terms and accept work on your own initiative.</p><Link className="text-link" href="/register">Create a worker account <ArrowUpRight size={16}/></Link><p className="small-note">Adult eligibility is required. Profile review does not mean identity verification.</p></div></section>
    <section className="editorial-section faq"><h2>Before you begin.</h2>{[
      ["Can an agent book work on its own?", "No. Agents create drafts and submit them for review. Owners select workers, and workers must accept assignments."],
      ["Does this move real money?", "No. This development preview uses simulated payments or Stripe test mode. It does not provide live payouts or escrow."],
      ["What stays private?", "Task messages and deliverables are restricted to participants and authorized administrators. Workers opt into public profile publication."],
      ["Can I run it locally for free?", "Yes. Deterministic planning and matching need no paid AI account. Optional inference uses local Ollama."],
      ["Is HumanLoop open for public bookings?", "Not yet. This is a portfolio and startup development project. Public use requires further security, safety, legal and operational review."]
    ].map(([q,a])=><details key={q}><summary>{q}</summary><p>{a}</p></details>)}</section>
    <section className="editorial-close"><h2>Start with a clear request.</h2><div className="actions"><Button asChild><Link href="/dashboard/tasks/new">Create a task draft <ArrowRight size={16}/></Link></Button><Link className="text-link" href="/developers/playground">Try the agent playground</Link></div></section>
  </div>;
}
