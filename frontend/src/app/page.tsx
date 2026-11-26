import Link from "next/link";
import { Logo } from "@/components/logo";

const features = [
  { title: "Text to image", body: "Describe it and get images from GPT Image or Gemini, at every size and quality they offer." },
  { title: "Edit and inpaint", body: "Upload a photo, mask an area, and change just that part." },
  { title: "Text and image to video", body: "Turn a prompt or a still into a clip with sound using Google Veo 3.1." },
  { title: "Copilot", body: "Not sure which model fits? Describe the goal and the copilot picks the model, settings and steps." },
  { title: "Auto-saved gallery", body: "Every result is saved to your workspace with its prompt and settings, ready to share." },
  { title: "Teams and roles", body: "Invite your team as admins, members or viewers. Everyone sees the same library." },
];

const models = ["GPT Image 2.6", "Nano Banana 2.1", "Gemini 3 Pro Image", "Veo 3.1"];

export default function Landing() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5">
        <Logo />
        <nav className="flex items-center gap-4 text-sm">
          <a href="#pricing" className="hidden text-zinc-400 hover:text-white sm:block">Pricing</a>
          <Link href="/login" className="text-zinc-300 hover:text-white">Sign in</Link>
          <Link href="/login?mode=signup" className="rounded-full bg-white px-4 py-2 font-medium text-black hover:bg-zinc-200">
            Start free
          </Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto max-w-4xl px-4 pb-20 pt-16 text-center sm:pt-24">
          <p className="mb-4 inline-block rounded-full border border-white/10 px-3 py-1 text-xs text-zinc-400">
            OpenAI and Google models, one studio
          </p>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-6xl">
            Create images and videos with{" "}
            <span className="bg-gradient-to-r from-violet-400 to-cyan-300 bg-clip-text text-transparent">every top model</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-zinc-400">
            Type a prompt, pick a model or let the copilot choose, and get results saved to your gallery automatically.
            Pay only for what you generate.
          </p>
          <div className="mt-10 flex flex-wrap justify-center gap-3">
            <Link href="/login?mode=signup" className="rounded-full bg-white px-6 py-3 font-medium text-black hover:bg-zinc-200">
              Get free credits
            </Link>
            <a href="#features" className="rounded-full border border-white/15 px-6 py-3 text-zinc-200 hover:bg-white/5">
              See what it does
            </a>
          </div>
          <div className="mt-12 flex flex-wrap justify-center gap-2 text-sm text-zinc-500">
            {models.map((m) => (
              <span key={m} className="rounded-md border border-white/10 px-3 py-1">{m}</span>
            ))}
          </div>
        </section>

        <section id="features" className="mx-auto grid max-w-6xl gap-4 px-4 pb-24 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div key={f.title} className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
              <h3 className="font-medium">{f.title}</h3>
              <p className="mt-2 text-sm text-zinc-400">{f.body}</p>
            </div>
          ))}
        </section>

        <section id="pricing" className="mx-auto max-w-3xl px-4 pb-24 text-center">
          <h2 className="text-3xl font-semibold tracking-tight">Simple, usage-based pricing</h2>
          <p className="mt-4 text-zinc-400">
            Every new account starts with free credits. After that, buy credits and pay the model&apos;s own price plus a
            small 10% platform fee. No subscription, no expiry surprises.
          </p>
          <Link href="/login?mode=signup" className="mt-8 inline-block rounded-full bg-white px-6 py-3 font-medium text-black hover:bg-zinc-200">
            Start with free credits
          </Link>
        </section>
      </main>

      <footer className="border-t border-white/10 py-8 text-center text-sm text-zinc-500">
        © {new Date().getFullYear()} AI Content Studio
      </footer>
    </div>
  );
}
