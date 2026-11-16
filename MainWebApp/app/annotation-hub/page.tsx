import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  Braces,
  FileJson2,
  Gamepad2,
  Layers3,
  MonitorDown,
  ShieldCheck,
  Video,
} from "lucide-react";

import { AppPage, PageHero, SectionCard, StatCard } from "@/components/app/page-primitives";

export const metadata: Metadata = {
  title: "Annotation Hub · AIHM",
  description: "Open AIHuMo browser annotation tools and find the desktop movement-analysis pipeline.",
};

const browserTools = [
  {
    title: "Workout Annotation Studio",
    description: "Load a local video, label activity, sets, repetitions, phases, and form, then export portable annotation JSON.",
    href: "/workouts/annotation",
    action: "Open annotation studio",
    icon: FileJson2,
  },
  {
    title: "Live Workout Studio",
    description: "Use the browser camera and pose tracker while keeping workout controls and session context on one page.",
    href: "/workouts",
    action: "Open workout studio",
    icon: Video,
  },
];

const desktopTools = [
  {
    title: "Mode 0 · Feature processing",
    description: "Generate canonical skeleton video, feature Parquet, metadata, and quality reports from source recordings.",
    icon: Braces,
  },
  {
    title: "Modes 1–4 · Review and alignment",
    description: "Annotate, align multiple cameras, inspect interactive graphs, and review synchronized 3D movement.",
    icon: Layers3,
  },
  {
    title: "Movement Game Hub",
    description: "Run calibrated target, balance, rhythm, reaction, rehabilitation, ergonomics, and gait game loops against processed features.",
    icon: Gamepad2,
  },
];

export default function AnnotationHubPage() {
  return (
    <AppPage>
      <PageHero
        eyebrow="Annotation hub"
        title="Move between browser annotation and the full desktop pipeline without leaving AIHM."
        description="Browser-ready tools stay inside this website and open in the same tab. The desktop application remains the processing workspace for canonical Parquet generation, multi-camera alignment, graph analysis, and movement games."
        actions={[
          { href: "/workouts/annotation", label: "Annotate in this browser" },
          { href: "/workouts", label: "Open live workout", secondary: true },
        ]}
        aside={
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <StatCard label="Browser navigation" value="In-page" detail="Annotation routes no longer open a separate window." icon={Activity} />
            <StatCard label="Video privacy" value="Local" detail="Selected annotation video bytes remain in this browser." icon={ShieldCheck} />
            <StatCard label="Shared format" value="JSON" detail="Web annotations remain portable to AIHuMo workflows." icon={FileJson2} />
          </div>
        }
      />

      <SectionCard
        eyebrow="Use now"
        title="Browser workspaces"
        description="These tools run directly inside the Vercel website and resize for desktop, tablet, and phone."
      >
        <div className="grid gap-4 md:grid-cols-2">
          {browserTools.map(({ title, description, href, action, icon: Icon }) => (
            <article key={href} className="rounded-[26px] border border-black/10 bg-white/70 p-6 shadow-[0_18px_40px_rgba(29,35,43,0.08)]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-xl font-semibold tracking-[-0.03em] text-foreground">{title}</h3>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{description}</p>
                </div>
                <div className="rounded-full bg-primary/10 p-3 text-primary"><Icon className="h-5 w-5" /></div>
              </div>
              <Link href={href} className="button-primary mt-6 inline-flex">{action}</Link>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="Desktop pipeline"
        title="Processing and advanced movement analysis"
        description="These features use native Python, PyQt6, OpenCV, MediaPipe, and local Parquet files. They remain in the downloadable desktop application rather than running inside Vercel."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          {desktopTools.map(({ title, description, icon: Icon }) => (
            <article key={title} className="rounded-[24px] border border-black/10 bg-background/70 p-5">
              <Icon className="h-5 w-5 text-primary" />
              <h3 className="mt-4 text-lg font-semibold text-foreground">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
            </article>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3 rounded-[22px] border border-black/10 bg-slate-950 px-5 py-5 text-white">
          <MonitorDown className="h-5 w-5" />
          <p className="min-w-0 flex-1 text-sm leading-6 text-white/75">Download or run the desktop repository when you need feature generation, native graphing, alignment, or the complete movement-game backend.</p>
          <a className="button-secondary" href="https://github.com/JacksonJ01/aihumo" rel="noreferrer">Open GitHub repository</a>
        </div>
      </SectionCard>
    </AppPage>
  );
}
