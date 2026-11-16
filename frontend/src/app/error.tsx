"use client";
export default function ErrorPage({reset}:{reset:()=>void}){return <div className="container section"><h1>Something interrupted the connection.</h1><p>Please try again. If the problem persists, check that the backend is running.</p><button className="button button-outline" onClick={reset}>Try again</button></div>;}
