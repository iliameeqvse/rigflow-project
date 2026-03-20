import Link from "next/link";

const quickActions = [
  {
    href: "/upload",
    title: "Upload model",
    description: "Send a character mesh to start the auto-rigging pipeline.",
  },
  {
    href: "/animations",
    title: "Animation library",
    description: "Browse reusable animations and pick one for retargeting.",
  },
  {
    href: "/upload-animation",
    title: "Publish animation",
    description: "Contribute your own clips to the shared team library.",
  },
  {
    href: "/login",
    title: "Sign in",
    description: "Access your rigs, projects, and saved animation drafts.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 px-6 py-16 text-slate-100">
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10">
      <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-10 shadow-2xl">
        <p className="text-xs uppercase tracking-[0.25em] text-cyan-400">
          RigFlow Workspace
        </p>
        <h1 className="mt-3 text-4xl font-bold md:text-5xl">
          Main page for rigging and animation operations
        </h1>
        <p className="mt-4 max-w-3xl text-lg text-slate-300">
            Centralize your 3D pipeline in one place: upload models, browse the
            animation library, and prepare assets for retargeting.
          </p>
          </section>

<section className="grid gap-4 sm:grid-cols-2">
  {quickActions.map((action) => (
    <Link
      key={action.href}
      href={action.href}
      className="group rounded-2xl border border-slate-800 bg-slate-900 p-6 transition hover:-translate-y-1 hover:border-cyan-400/60 hover:bg-slate-800"
    >
      <h2 className="text-xl font-semibold text-slate-100 group-hover:text-cyan-300">
        {action.title}
      </h2>
      <p className="mt-2 text-sm leading-6 text-slate-400">
        {action.description}
      </p>
    </Link>
  ))}
</section>
</main>
</div>
);
}