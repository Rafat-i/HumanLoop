import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AuthView } from "@/components/auth-view";
import { MarketplaceView } from "@/components/marketplace-view";
import { TaskForm, TaskView } from "@/components/task-view";
import { Overview } from "@/components/workspace";
import { QueryClient, QueryClientProvider } from "@/lib/query";
const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/dashboard" }));
function wrap(view: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient()}>{view}</QueryClientProvider>); }
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }); }

describe("connected frontend flows", () => {
 it("validates an authentication form before making a request", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher); wrap(<AuthView mode="login"/>);
  fireEvent.change(screen.getByLabelText("Email address"), {target:{value:"person@example.com"}});
  fireEvent.change(screen.getByLabelText("Password"), {target:{value:"short"}});
  fireEvent.submit(screen.getByRole("button",{name:"Sign in"}).closest("form")!);
  expect(await screen.findByText("Use at least 12 characters")).toBeInTheDocument(); expect(fetcher).not.toHaveBeenCalled();
 });
 it("sends login credentials and routes to the workspace", async () => {
  const fetcher = vi.fn().mockResolvedValue(json({id:"user"})); vi.stubGlobal("fetch",fetcher); wrap(<AuthView mode="login"/>);
  fireEvent.change(screen.getByLabelText("Email address"),{target:{value:"person@example.com"}});
  fireEvent.change(screen.getByLabelText("Password"),{target:{value:"a-long-test-password"}});
  fireEvent.submit(screen.getByRole("button",{name:"Sign in"}).closest("form")!);
  await waitFor(()=>expect(push).toHaveBeenCalledWith("/dashboard"));
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({email:"person@example.com",password:"a-long-test-password"});
 });
 it("applies marketplace filters to the backend query", async () => {
  const fetcher=vi.fn().mockImplementation(()=>Promise.resolve(json({items:[],total:0,page:1,limit:12})));vi.stubGlobal("fetch",fetcher);wrap(<MarketplaceView/>);
  expect(await screen.findByText("No matches yet")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search"),{target:{value:"research"}});
  fireEvent.change(screen.getByLabelText("Category"),{target:{value:"Retail checks"}});
  await waitFor(()=>expect(fetcher.mock.calls.some(([url])=>String(url).includes("q=research")&&String(url).includes("category=Retail+checks"))).toBe(true));
 });
 it("shows honest loading and failure states", async () => {
  let reject: (reason: Error) => void = ()=>{};
  vi.stubGlobal("fetch",vi.fn().mockImplementation(()=>new Promise((_resolve,r)=>{reject=r;})));
  wrap(<MarketplaceView/>);expect(screen.getByRole("status",{name:"Loading"})).toBeInTheDocument();
  reject(new Error("Backend unavailable"));expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
 });
 it("creates a task with integer currency units and normalized skills", async () => {
  const fetcher=vi.fn().mockResolvedValue(json({id:"new-task"},201));vi.stubGlobal("fetch",fetcher);wrap(<TaskForm/>);
  fireEvent.change(screen.getByLabelText("Task title"),{target:{value:"Check public opening hours"}});
  fireEvent.change(screen.getByLabelText("Describe the outcome"),{target:{value:"Confirm the posted public opening hours at a shop."}});
  fireEvent.change(screen.getByLabelText("Required skills (comma separated)"),{target:{value:"research, french"}});
  fireEvent.submit(screen.getByRole("button",{name:"Create draft task"}).closest("form")!);
  await waitFor(()=>expect(push).toHaveBeenCalledWith("/tasks/new-task"));
  const body=JSON.parse(fetcher.mock.calls[0][1].body);expect(body.budget).toBe(3000);expect(body.required_skills).toEqual(["research","french"]);
 });
 it("submits a worker application through the actual form", async () => {
  const fetcher=vi.fn().mockImplementation((url: string, options:RequestInit={})=>{
   if(url.endsWith("/auth/me"))return Promise.resolve(json({id:"worker",roles:["worker"],display_name:"Worker"}));
   if(options.method==="POST")return Promise.resolve(json({id:"application"},201));
   return Promise.resolve(json({id:"task",owner_id:"owner",assigned_worker_id:null,title:"Public task",description:"A clear description of a public task.",category:"Retail checks",city:"Toronto",budget:3000,currency:"CAD",status:"OPEN",payment_status:"UNPAID",expected_minutes:60,required_skills:[]}));
  });vi.stubGlobal("fetch",fetcher);wrap(<TaskView id="task"/>);
  fireEvent.change(await screen.findByLabelText("Your proposal"),{target:{value:"I will provide a concise report."}});
  fireEvent.submit(screen.getByRole("button",{name:"Apply for this task"}).closest("form")!);
  await waitFor(()=>expect(fetcher.mock.calls.some(([url,options])=>url==="/api/v1/tasks/task/applications"&&JSON.parse(options.body).compensation===3000)).toBe(true));
 });
 it("renders dashboard counts from the API", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(json({tasks_created:7,tasks_completed:2,client_completion_rate:25,active_applications:1,test_earnings:[],statuses:[],unread_messages:3})));
  wrap(<Overview user={{id:"client",display_name:"Demo Client",email:"client@example.com",roles:["client"],email_verified:true,demo:true}}/>);
  expect(await screen.findByText("7")).toBeInTheDocument();expect(screen.getByText("25%")).toBeInTheDocument();
 });
});


it("edits an existing draft without losing private visibility or its deadline", async () => {
 const fetcher=vi.fn().mockResolvedValue(json({id:"draft"}));vi.stubGlobal("fetch",fetcher);
 const onSaved=vi.fn().mockResolvedValue(undefined);
 wrap(<TaskForm task={{id:"draft",owner_id:"owner",assigned_worker_id:null,title:"Existing task title",description:"An existing description of the public information request.",category:"Retail checks",required_skills:["research"],city:"Toronto",budget:3000,currency:"CAD",expected_minutes:60,requirements:"Keep this scope",visibility:"PRIVATE",deadline:"2027-01-01T12:00:00Z",status:"DRAFT",payment_status:"UNPAID",demo:true,created_at:"2026-10-24T12:00:00Z"}} onSaved={onSaved}/>);
 expect(screen.getByLabelText("Task title")).toHaveValue("Existing task title");
 fireEvent.change(screen.getByLabelText("Task title"),{target:{value:"Revised task title"}});
 fireEvent.submit(screen.getByRole("button",{name:"Save draft"}).closest("form")!);
 await waitFor(()=>expect(onSaved).toHaveBeenCalled());
 expect(fetcher.mock.calls[0][0]).toBe("/api/v1/tasks/draft");
 expect(fetcher.mock.calls[0][1].method).toBe("PUT");
 expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({title:"Revised task title",visibility:"PRIVATE",deadline:"2027-01-01T12:00:00Z",requirements:"Keep this scope",budget:3000});
});


it("deletes an owned draft only after confirmation and returns to the task list", async () => {
 vi.spyOn(window,"confirm").mockReturnValue(true);
 const fetcher=vi.fn().mockImplementation((url:string,options:RequestInit={})=>{
  if(options.method==="DELETE")return Promise.resolve(new Response(null,{status:204}));
  if(url.endsWith("/auth/me"))return Promise.resolve(json({id:"owner",roles:["client"]}));
  if(url==="/api/v1/tasks/draft-delete")return Promise.resolve(json({id:"draft-delete",owner_id:"owner",assigned_worker_id:null,title:"Draft to remove",description:"Fictional task description for deletion.",category:"Retail checks",city:"Toronto",budget:3000,currency:"CAD",status:"DRAFT",payment_status:"UNPAID",expected_minutes:60,required_skills:[]}));
  return Promise.resolve(json([]));
 });vi.stubGlobal("fetch",fetcher);wrap(<TaskView id="draft-delete"/>);
 fireEvent.click(await screen.findByRole("button",{name:"Delete draft"}));
 await waitFor(()=>expect(push).toHaveBeenCalledWith("/dashboard/tasks"));
 expect(fetcher.mock.calls.some(([url,options])=>url==="/api/v1/tasks/draft-delete"&&options.method==="DELETE")).toBe(true);
});
