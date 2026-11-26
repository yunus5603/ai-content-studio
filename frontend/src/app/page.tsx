import Link from "next/link";
import {
  IconArrowRight,
  IconBrush,
  IconCheck,
  IconGrid,
  IconImage,
  IconPlay,
  IconSparkles,
  IconUsers,
  IconVideo,
  IconWand,
} from "@/components/icons";
import { Logo, LogoMark } from "@/components/logo";
import { AutoVideo, Reveal } from "@/components/reveal";
import { SAMPLES } from "@/lib/samples";

const features = [
  {
    icon: IconImage,
    title: "Text to image",
    body: "Describe it and get images from GPT Image or Gemini, at every size and quality they offer.",
  },
  { icon: IconBrush, title: "Edit and inpaint", body: "Upload a photo, paint over an area, and change just that part." },
  {
    icon: IconVideo,
    title: "Text and image to video",
    body: "Turn a prompt or a still into a clip with sound using Google Veo 3.1.",
  },
  {
    icon: IconWand,
    title: "Copilot",
    body: "Not sure which model fits? Describe the goal and the copilot picks the model, settings and steps.",
  },
  {
    icon: IconGrid,
    title: "Auto-saved gallery",
    body: "Every result is saved to your workspace with its prompt and settings, ready to share.",
  },
  {
    icon: IconUsers,
    title: "Teams and roles",
    body: "Invite your team as admins, members or viewers. Everyone works from the same library.",
  },
];

const models = ["GPT Image 2.6", "Nano Banana 2.1", "Gemini 3 Pro Image", "Veo 3.1", "Veo 3.1 Fast"];

const steps = [
  { n: "01", title: "Describe", body: "Write what you want, or drop in a reference image. Enhance the prompt with one click." },
  { n: "02", title: "Pick or let the copilot pick", body: "Choose a model and its settings, or let the copilot choose for you." },
  { n: "03", title: "Generate and share", body: "Watch it render, then find it in your gallery with a share link ready." },
];

const byId = Object.fromEntries(SAMPLES.map((s) => [s.id, s]));

function Header() {
  return (
    <header className="glass sticky top-0 z-40 border-b border-line/70">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3.5">
        <Logo />
        <nav className="flex items-center gap-1 text-sm sm:gap-2">
          <a href="#showcase" className="btn btn-ghost hidden md:inline-flex">Showcase</a>
          <a href="#features" className="btn btn-ghost hidden md:inline-flex">Features</a>
          <a href="#pricing" className="btn btn-ghost hidden sm:inline-flex">Pricing</a>
          <Link href="/login" className="btn btn-ghost">Sign in</Link>
          <Link href="/login?mode=signup" className="btn btn-primary">Start free</Link>
        </nav>
      </div>
    </header>
  );
}

function HeroVisual() {
  const hero = byId.aurora;
  return (
    <div className="relative mx-auto mt-16 max-w-5xl animate-fade-up [animation-delay:.35s]">
      {/* floating sample cards */}
      <div className="absolute -left-10 top-16 z-10 hidden w-44 animate-float lg:block">
        <div className="card overflow-hidden p-1.5 shadow-float">
          {/* eslint-disable-next-line @next/next/no-img-element -- static showcase asset */}
          <img src={byId.orbs.src} alt="Pastel spheres sample" className="aspect-square w-full rounded-[10px] object-cover" />
          <p className="px-1.5 pb-1 pt-2 text-[11px] text-muted">Product shot · 1:1</p>
        </div>
      </div>
      <div className="absolute -right-8 bottom-14 z-10 hidden w-40 animate-float [animation-delay:-3s] lg:block">
        <div className="card overflow-hidden p-1.5 shadow-float">
          {/* eslint-disable-next-line @next/next/no-img-element -- static showcase asset */}
          <img src={byId.silk.src} alt="Abstract silk sample" className="aspect-[4/5] w-full rounded-[10px] object-cover" />
          <p className="px-1.5 pb-1 pt-2 text-[11px] text-muted">Abstract · 4:5</p>
        </div>
      </div>

      {/* studio window */}
      <div className="card overflow-hidden p-2 shadow-float">
        <div className="flex items-center gap-1.5 px-2 pb-2 pt-1">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-3 text-xs text-subtle">studio / create</span>
        </div>
        <div className="relative overflow-hidden rounded-xl">
          <AutoVideo src={hero.video!} poster={hero.src} className="aspect-video w-full object-cover" />
          <div className="absolute inset-x-3 bottom-3 sm:inset-x-6 sm:bottom-6">
            <div className="glass flex items-center gap-3 rounded-2xl border border-white/60 p-2 pl-4 shadow-float">
              <IconSparkles className="h-4 w-4 shrink-0 text-brand" />
              <p className="line-clamp-1 flex-1 text-left text-sm text-ink-2">{hero.prompt}</p>
              <span className="hidden rounded-full bg-surface-2 px-2.5 py-1 text-xs text-muted sm:inline">Veo 3.1 · 8s</span>
              <span className="btn btn-brand btn-sm">Generate</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Marquee() {
  const row = [...SAMPLES, ...SAMPLES];
  return (
    <div className="relative mt-24 overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]">
      <div className="flex w-max animate-marquee gap-4 hover:[animation-play-state:paused]">
        {row.map((s, i) => (
          // eslint-disable-next-line @next/next/no-img-element -- static showcase asset
          <img
            key={`${s.id}-${i}`}
            src={s.src}
            alt=""
            className="h-40 w-64 rounded-2xl border border-line object-cover shadow-soft"
            loading="lazy"
          />
        ))}
      </div>
    </div>
  );
}

function Showcase() {
  const layout: Record<string, string> = {
    aurora: "md:col-span-2 md:row-span-2",
    orbs: "",
    silk: "md:row-span-2",
    alpine: "md:col-span-2",
    dunes: "",
    planet: "md:col-span-2",
  };
  const order = ["aurora", "orbs", "silk", "dunes", "alpine", "planet"];
  return (
    <section id="showcase" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-24">
      <Reveal className="mx-auto max-w-2xl text-center">
        <p className="label">Showcase</p>
        <h2 className="text-3xl font-semibold tracking-tight sm:text-5xl">From one line to a finished shot</h2>
        <p className="mt-4 text-muted">Hover any piece to see the kind of prompt behind it. Every prompt here is one click away in the studio.</p>
      </Reveal>
      <div className="mt-12 grid auto-rows-[220px] grid-cols-1 gap-4 md:grid-flow-dense md:grid-cols-4">
        {order.map((id, i) => {
          const s = byId[id];
          return (
            <Reveal key={id} delay={i * 0.06} className={`${layout[id]} min-h-0`}>
              <figure className="group relative h-full overflow-hidden rounded-2xl border border-line bg-surface-2 shadow-soft">
                {s.video ? (
                  <AutoVideo
                    src={s.video}
                    poster={s.src}
                    className="h-full w-full object-cover transition duration-700 ease-out group-hover:scale-[1.04]"
                  />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element -- static showcase asset
                  <img
                    src={s.src}
                    alt={s.title}
                    loading="lazy"
                    className="h-full w-full object-cover transition duration-700 ease-out group-hover:scale-[1.04]"
                  />
                )}
                <span className="glass absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium text-ink-2">
                  {s.media === "video" || s.video ? <IconPlay className="h-3 w-3" /> : <IconImage className="h-3 w-3" />}
                  {s.video && s.media === "image" ? "Image + motion" : s.tag}
                </span>
                <figcaption className="absolute inset-x-0 bottom-0 translate-y-3 bg-gradient-to-t from-black/75 via-black/30 to-transparent p-4 pt-14 text-white opacity-0 transition duration-500 ease-out group-hover:translate-y-0 group-hover:opacity-100">
                  <p className="text-sm font-medium">{s.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-white/80">“{s.prompt}”</p>
                </figcaption>
              </figure>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}

function Features() {
  return (
    <section id="features" className="scroll-mt-20 border-y border-line bg-surface py-24">
      <div className="mx-auto max-w-6xl px-4">
        <Reveal className="max-w-2xl">
          <p className="label">Everything in one studio</p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-5xl">
            Every model. <span className="text-subtle">One clean workflow.</span>
          </h2>
        </Reveal>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 0.08}>
              <div className="card card-hover h-full p-6">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-soft text-brand">
                  <f.icon />
                </span>
                <h3 className="mt-5 font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{f.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-24 lg:grid-cols-2">
      <div>
        <Reveal>
          <p className="label">How it works</p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Three steps, no setup</h2>
        </Reveal>
        <ol className="mt-10 space-y-3">
          {steps.map((s, i) => (
            <Reveal as="li" key={s.n} delay={i * 0.1}>
              <div className="card card-hover flex gap-5 p-5">
                <span className="font-mono text-sm text-brand">{s.n}</span>
                <div>
                  <h3 className="font-semibold">{s.title}</h3>
                  <p className="mt-1 text-sm text-muted">{s.body}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
      <Reveal delay={0.15}>
        <div className="relative">
          <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-brand-soft via-[#fde7f0] to-[#fff1e0]" />
          <div className="card overflow-hidden p-2 shadow-float">
            <AutoVideo src={byId.alpine.video!} poster={byId.alpine.src} className="aspect-video w-full rounded-xl object-cover" />
            <div className="flex items-center justify-between gap-3 px-2 pb-1 pt-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">Alpine flyover</p>
                <p className="truncate text-xs text-subtle">Veo 3.1 · 16:9 · 8 seconds · with audio</p>
              </div>
              <span className="chip shrink-0">
                <span className="h-1.5 w-1.5 rounded-full bg-success" /> Saved to gallery
              </span>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

function Pricing() {
  const points = [
    "Free credits when you sign up",
    "Pay the model's own price plus a 10% platform fee",
    "Credit packs via Stripe, no subscription",
    "Team spending limits and usage reports",
  ];
  return (
    <section id="pricing" className="mx-auto max-w-6xl scroll-mt-20 px-4 pb-24">
      <Reveal>
        <div className="card grid overflow-hidden lg:grid-cols-[1.1fr_1fr]">
          <div className="p-8 sm:p-12">
            <p className="label">Pricing</p>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Simple, usage-based pricing</h2>
            <p className="mt-4 max-w-md text-muted">
              Start with free credits. After that, buy credits and pay only for what you generate. No expiry surprises.
            </p>
            <ul className="mt-8 space-y-3 text-sm">
              {points.map((p) => (
                <li key={p} className="flex items-center gap-3">
                  <span className="grid h-5 w-5 place-items-center rounded-full bg-success/10 text-success">
                    <IconCheck className="h-3.5 w-3.5" />
                  </span>
                  {p}
                </li>
              ))}
            </ul>
            <Link href="/login?mode=signup" className="btn btn-primary btn-lg mt-10">
              Start with free credits <IconArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="relative min-h-72 bg-surface-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- static showcase asset */}
            <img src={byId.dunes.src} alt="" className="absolute inset-0 h-full w-full object-cover" loading="lazy" />
            <div className="absolute inset-x-6 bottom-6 grid grid-cols-2 gap-3">
              <div className="glass rounded-2xl p-4 shadow-card">
                <p className="text-xs text-muted">Model price</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">$0.040</p>
              </div>
              <div className="glass rounded-2xl p-4 shadow-card">
                <p className="text-xs text-muted">You pay</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">$0.044</p>
              </div>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="mx-auto max-w-6xl px-4 pb-24">
      <Reveal>
        <div className="relative overflow-hidden rounded-[2rem] px-6 py-20 text-center text-white">
          <AutoVideo src={byId.silk.video!} poster={byId.silk.src} className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-b from-[#1b1446]/60 to-[#1b1446]/80" />
          <div className="relative">
            <LogoMark className="mx-auto h-11 w-11" />
            <h2 className="mt-6 text-3xl font-semibold tracking-tight sm:text-5xl">Your next shot is one prompt away</h2>
            <p className="mx-auto mt-4 max-w-xl text-white/80">Sign up in seconds and try every model with free credits.</p>
            <Link href="/login?mode=signup" className="btn btn-lg mt-8 bg-white text-ink hover:bg-white/90">
              Get free credits <IconArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen overflow-x-clip">
      <Header />
      <main>
        <section className="relative px-4 pt-16 sm:pt-24">
          {/* soft color field */}
          <div aria-hidden className="pointer-events-none absolute inset-x-0 -top-24 -z-10 h-[720px] overflow-hidden">
            <div className="absolute left-[8%] top-10 h-80 w-80 animate-blob rounded-full bg-[#c9c2ff] opacity-60 blur-3xl" />
            <div className="absolute right-[10%] top-24 h-96 w-96 animate-blob rounded-full bg-[#ffc4da] opacity-60 blur-3xl [animation-delay:-6s]" />
            <div className="absolute left-[40%] top-64 h-72 w-72 animate-blob rounded-full bg-[#ffe1bd] opacity-70 blur-3xl [animation-delay:-12s]" />
            <div className="absolute inset-0 bg-[radial-gradient(#16151a10_1px,transparent_1px)] [background-size:22px_22px] [mask-image:radial-gradient(ellipse_at_top,#000_30%,transparent_70%)]" />
          </div>

          <div className="mx-auto max-w-4xl text-center">
            <Link href="/login?mode=signup" className="eyebrow animate-fade-up">
              <span className="rounded-full bg-brand px-2 py-0.5 text-[11px] font-semibold text-white">New</span>
              Veo 3.1 video with sound is live
              <IconArrowRight className="h-3.5 w-3.5" />
            </Link>
            <h1 className="mt-6 animate-fade-up text-[2.6rem] font-semibold leading-[1.05] tracking-tight [animation-delay:.08s] sm:text-7xl">
              Create images and videos with <span className="text-gradient">every top model</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl animate-fade-up text-lg text-muted [animation-delay:.16s]">
              Type a prompt, pick a model or let the copilot choose, and get results saved to your gallery automatically. Pay
              only for what you generate.
            </p>
            <div className="mt-9 flex animate-fade-up flex-wrap justify-center gap-3 [animation-delay:.24s]">
              <Link href="/login?mode=signup" className="btn btn-brand btn-lg">
                Get free credits <IconArrowRight className="h-4 w-4" />
              </Link>
              <a href="#showcase" className="btn btn-secondary btn-lg">
                <IconPlay className="h-3.5 w-3.5" /> See examples
              </a>
            </div>
            <div className="mt-10 flex animate-fade-up flex-wrap justify-center gap-2 [animation-delay:.3s]">
              {models.map((m) => (
                <span key={m} className="chip">{m}</span>
              ))}
            </div>
          </div>

          <HeroVisual />
        </section>

        <Marquee />
        <Showcase />
        <Features />
        <HowItWorks />
        <Pricing />
        <FinalCta />
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 text-sm text-subtle sm:flex-row">
          <div className="flex items-center gap-2">
            <LogoMark className="h-5 w-5" /> © {new Date().getFullYear()} AI Content Studio
          </div>
          <p className="text-xs">Showcase visuals are illustrative renders made for this site.</p>
        </div>
      </footer>
    </div>
  );
}
