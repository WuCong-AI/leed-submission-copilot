import Link from "next/link";
import { ProjectCard } from "../../../components/workspace";
export default function Dashboard() { return <main className="shell"><h1>Project dashboard</h1><p><Link href="/app/projects/new">Create project</Link></p><section className="grid"><ProjectCard name="v5 BD+C Demo Office" version="v5" family="BD+C" phase="concept" /><ProjectCard name="v5 ID+C Demo Fit-out" version="v5" family="ID+C" phase="design development" /><ProjectCard name="v4.1 O+M Demo Existing Office" version="v4.1" family="O+M" phase="submission" /></section></main>; }
