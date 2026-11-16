import { test, expect, request as requestFactory, type Page } from "@playwright/test";
import { mkdir, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
const root = path.resolve(process.cwd(), "..");
const mailDirectory = process.env.E2E_MAIL_DIR || path.join(root, "local-mail");
const password = `Test-${randomUUID()}-Aa1`;
async function register(page: Page, email: string, role: string, name: string) {
 await page.goto("/register");
 await page.getByLabel("Display name", {exact:true}).fill(name);
 await page.getByLabel("Email address").fill(email);
 await page.getByLabel("Password", {exact:true}).fill(password);
 await page.getByLabel("I want to").selectOption(role);
 await page.getByLabel("I confirm that I am 18 or older.").check();
 await page.getByRole("button", {name:"Create account",exact:true}).click();
 await expect(page.getByRole("status").filter({hasText:"Account created"})).toBeVisible();
 let link = "";
 await expect.poll(async()=>{
  for (const file of await readdir(mailDirectory)) {
   if (!file.endsWith(".json")) continue;
   const item = JSON.parse(await readFile(path.join(mailDirectory,file),"utf8"));
   if (item.to===email && item.purpose==="verify") link=item.url;
  }
  return link;
 }).not.toBe("");
 await page.goto(link); await page.getByRole("button",{name:"Verify email from this link"}).click();
 await expect(page.getByText("Email verified",{exact:true})).toBeVisible();
 await login(page,email,password);
}
async function login(page:Page,email:string,secret:string){
 await page.goto("/login"); await page.getByLabel("Email address").fill(email); await page.getByLabel("Password",{exact:true}).fill(secret);
 await page.getByRole("button",{name:"Sign in",exact:true}).click(); await expect(page).toHaveURL(/\/dashboard$/);
}
test("complete human workflow, agent draft, and local MCP connection", async({browser,request})=>{
 const adminEmail=process.env.E2E_ADMIN_EMAIL;const adminPassword=process.env.E2E_ADMIN_PASSWORD;
 if(!adminEmail||!adminPassword)throw new Error("Provision a development admin and set E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD. Use a disposable local database.");
 const workerContext=await browser.newContext({baseURL:process.env.E2E_BASE_URL||"http://localhost:3000"});const clientContext=await browser.newContext({baseURL:process.env.E2E_BASE_URL||"http://localhost:3000"});const adminContext=await browser.newContext({baseURL:process.env.E2E_BASE_URL||"http://localhost:3000"});
 const worker=await workerContext.newPage();const client=await clientContext.newPage();const admin=await adminContext.newPage();
 for(const page of [worker,client,admin])page.on("dialog",dialog=>dialog.accept());
 const suffix=randomUUID().slice(0,8);const name=`Worker ${suffix}`;
 await register(worker,`worker-${suffix}@example.com`,"worker",name);
 await worker.goto("/dashboard/profile");
 await worker.getByLabel("Public display name").fill(name);await worker.getByLabel("Professional headline").fill("Careful public information research");
 await worker.getByLabel("About you").fill("Fictional automated-test worker with experience documenting public information.");
 await worker.getByLabel("Approximate city").fill("Toronto");await worker.getByLabel("Skills (comma separated)").fill("research");
 await worker.getByLabel("I choose to publish these profile fields").selectOption("Yes");await worker.locator("form").filter({has:worker.getByLabel("Public display name")}).getByRole("button",{name:"Save",exact:true}).click();
 await expect(worker.getByText(/Profile review: PENDING/)).toBeVisible();
 await login(admin,adminEmail,adminPassword);await admin.goto("/admin/workers");
 await admin.getByRole("row").filter({hasText:name}).getByRole("button",{name:"approve",exact:true}).click();
 await expect(admin.getByRole("row").filter({hasText:name})).toContainText("APPROVED");
 await register(client,`client-${suffix}@example.com`,"client",`Client ${suffix}`);
 await client.goto("/marketplace");await client.getByLabel("Search",{exact:true}).fill(name);await expect(client.getByRole("heading",{name,exact:true})).toBeVisible();
 await client.goto("/dashboard/tasks/new");await client.getByLabel("Task title").fill(`Public information test ${suffix}`);await client.getByLabel("Describe the outcome").fill("Document publicly posted opening hours. This is an automated fictional test; do not visit any location.");await client.getByLabel("Approximate city").fill("Toronto");await client.getByLabel("Required skills (comma separated)").fill("research");await client.getByRole("button",{name:"Create draft task"}).click();
 await expect(client).toHaveURL(/\/tasks\/[a-f0-9-]+$/);const taskUrl=client.url();const taskId=taskUrl.split("/").pop()!;
 await client.getByRole("button",{name:"Edit draft",exact:true}).click();
 await client.getByLabel("Task title").fill(`Revised public information test ${suffix}`);
 await client.getByRole("button",{name:"Save draft",exact:true}).click();
 await expect(client.getByRole("heading",{name:`Revised public information test ${suffix}`,exact:true})).toBeVisible();
 await client.getByRole("button",{name:"Submit for approval",exact:true}).click();await client.getByRole("button",{name:"Approve & publish in demo"}).click();await expect(client.getByText("open",{exact:true})).toBeVisible();
 await worker.goto(taskUrl);await worker.getByLabel("Your proposal").fill("I can document the publicly available information in a concise report.");await worker.getByRole("button",{name:"Apply for this task"}).click();await expect(worker.getByText("Saved successfully.",{exact:true})).toBeVisible();
 await client.reload();await client.getByRole("button",{name:"Select worker"}).click();await expect(client.getByText("assigned",{exact:true})).toBeVisible();
 await worker.reload();await worker.getByRole("button",{name:"Accept & start work"}).click();await worker.getByLabel("Message",{exact:true}).fill("I have accepted the scope.");await worker.getByRole("button",{name:"Send message",exact:true}).click();
 await client.reload();await expect(client.getByText("I have accepted the scope.",{exact:true})).toBeVisible();
 await worker.getByLabel("Completion report").fill("Fictional test report: the publicly displayed hours have been recorded. No actual visit occurred.");await worker.getByRole("button",{name:"Submit results",exact:true}).click();
 await client.reload();await client.getByRole("button",{name:"Approve completion"}).click();await client.getByRole("button",{name:"Create test payment"}).click();
 await client.goto("/dashboard/payments");await client.getByRole("row").filter({has:client.locator(`a[href="/tasks/${taskId}"]`)}).getByRole("button",{name:"Complete simulated payment"}).click();await expect(client.getByText("succeeded",{exact:true})).toBeVisible();
 await worker.goto("/dashboard/analytics");await expect(worker.getByText("Work completed",{exact:true})).toBeVisible();await expect(worker.getByText("$30.00 CAD")).toBeVisible();
 expect((await request.get(`/api/v1/tasks/${taskId}/messages`)).status()).toBe(401);
 const origin=new URL(client.url()).origin;
 const keyResponse=await clientContext.request.post("/api/v1/keys",{headers:{Origin:origin},data:{name:"E2E agent",scopes:["workers:read","tasks:read","tasks:write"]}});expect(keyResponse.status()).toBe(201);const key=(await keyResponse.json()).key;
 const agent=await requestFactory.newContext({baseURL:origin,extraHTTPHeaders:{Authorization:`Bearer ${key}`}});
 const draft=await agent.post("/api/v1/agent/tasks/drafts",{headers:{"Idempotency-Key":randomUUID()},data:{title:"Agent test draft",description:"A fictional request for public retail information only.",category:"Retail checks",city:"Toronto",budget:3000}});expect(draft.status()).toBe(201);expect((await draft.json()).status).toBe("DRAFT");
 const output=execFileSync(process.env.PYTHON_EXECUTABLE||"python",[path.join(root,"mcp-server","client_demo.py")],{env:{...process.env,HUMANLOOP_API_KEY:key,HUMANLOOP_API_URL:process.env.E2E_API_URL||"http://127.0.0.1:8000/api/v1"},encoding:"utf8",timeout:30000});expect(output).toContain("Available tools:");
 const otherKeyResponse=await workerContext.request.post("/api/v1/keys",{headers:{Origin:origin},data:{name:"MCP ownership check",scopes:["tasks:read"]}});
 expect(otherKeyResponse.status()).toBe(201);
 const otherKey=(await otherKeyResponse.json()).key;
 const verification=execFileSync(process.env.PYTHON_EXECUTABLE||"python",[path.join(root,"mcp-server","verify_integration.py")],{env:{...process.env,HUMANLOOP_API_KEY:key,HUMANLOOP_OTHER_API_KEY:otherKey,HUMANLOOP_VERIFY_DEVELOPMENT:"true",HUMANLOOP_API_URL:process.env.E2E_API_URL||"http://127.0.0.1:8000/api/v1"},encoding:"utf8",timeout:60000});
 expect(verification).toContain("MCP integration passed");
 if(process.env.E2E_VISUAL_DIR){
  test.setTimeout(300000);
  const directory=process.env.E2E_VISUAL_DIR;
  await mkdir(directory,{recursive:true});
  const publicContext=await browser.newContext({baseURL:origin});
  const publicPage=await publicContext.newPage();await publicPage.goto("/");
  // Exercise worker consent and keep generated test identities out of presentation captures.
  await worker.goto("/dashboard/profile");await worker.getByLabel("I choose to publish these profile fields").selectOption("No");await worker.locator("form").filter({has:worker.getByLabel("Public display name")}).getByRole("button",{name:"Save",exact:true}).click();
  await expect(worker.getByText("Saved successfully.",{exact:true})).toBeVisible();
  const profiles=await clientContext.request.get("/api/v1/workers/showcase");
  const workerId=(await profiles.json())[0].id;
  const views:[Page,string,string][]=[[publicPage,"/","landing"],[publicPage,"/marketplace","marketplace"],[publicPage,`/marketplace/workers/${workerId}`,"worker-profile"],[publicPage,"/login","login"],[publicPage,"/register","register"],[client,"/dashboard","client-dashboard"],[worker,"/dashboard","worker-dashboard"],[client,"/developers/playground","playground"],[client,"/developers/api-keys","api-keys"],[client,`/tasks/${taskId}`,"task"],[client,"/dashboard/payments","payments"],[admin,"/admin/workers","admin"]];
  for(const [page,route,label] of views){
   if(process.env.E2E_VISUAL_PAGES&&!process.env.E2E_VISUAL_PAGES.split(",").includes(label))continue;
   await page.goto(route);await page.waitForLoadState("networkidle");
   await expect(page.getByText("Too many requests; retry in one minute",{exact:false})).toHaveCount(0);
   if(page===client||page===worker||page===admin)await expect(page.getByText("Your workspace awaits",{exact:true})).toHaveCount(0);
   for(const [width,height] of [[1440,1000],[768,1024],[390,844]]){
    for(const theme of ["light","dark"]){
     await page.setViewportSize({width,height});
     await page.evaluate(value=>{localStorage.setItem("humanloop-theme",value);document.documentElement.classList.toggle("dark",value==="dark");window.dispatchEvent(new Event("humanloop-theme"));},theme);
     await page.screenshot({path:path.join(directory,`${label}-${width}-${theme}.png`),fullPage:label==="landing",animations:"disabled"});
     const overflow=await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth,elements:Array.from(document.querySelectorAll("body *")).filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>({tag:el.tagName,class:el.className,right:el.getBoundingClientRect().right})).slice(0,12)}));
     expect(overflow.width<=overflow.viewport+1,`${label} ${width} ${theme}: ${JSON.stringify(overflow)}`).toBe(true);
    }
   }
  }
  await publicContext.close();
 }
 await agent.dispose();await workerContext.close();await clientContext.close();await adminContext.close();
});
