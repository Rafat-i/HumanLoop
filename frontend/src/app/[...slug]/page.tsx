import { AuthView } from "@/components/auth-view";
import { MarketplaceView,WorkerView } from "@/components/marketplace-view";
import { TaskView } from "@/components/task-view";
import { Workspace } from "@/components/workspace";
import { AdminView } from "@/components/admin-view";
import { InfoView } from "@/components/info-view";
export default async function Page({params}:{params:Promise<{slug:string[]}>}){
 const {slug}=await params;const path=slug.join("/");
 if(["login","register","forgot-password","reset-password","verify-email"].includes(path))return <AuthView mode={path}/>;
 if(path==="marketplace")return <MarketplaceView/>;
 if(slug[0]==="marketplace"&&slug[1]==="workers"&&slug[2])return <WorkerView id={slug[2]}/>;
 if(path==="tasks")return <MarketplaceView tasks/>;
 if(slug[0]==="tasks"&&slug[1])return <TaskView id={slug[1]}/>;
 if(slug[0]==="dashboard")return <Workspace section={slug.slice(1).join("/")||"overview"}/>;
 if(slug[0]==="admin")return <AdminView section={slug[1]||"overview"}/>;
 if(slug[0]==="developers"&&slug[1]&&slug[1]!=="docs")return <Workspace developer section={slug[1]}/>;
 return <InfoView section={path}/>;
}
