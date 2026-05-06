import { Hero } from "@/components/landing/Hero";
import { Pipeline } from "@/components/landing/Pipeline";
import { Marquee } from "@/components/landing/Marquee";
import { Features } from "@/components/landing/Features";
import { FinalCTA } from "@/components/landing/FinalCTA";
import { Footer } from "@/components/landing/Footer";
import { ScrollProgress } from "@/components/landing/ScrollProgress";
import { FloatingCTA } from "@/components/landing/FloatingCTA";

export default function Home() {
  return (
    <>
      <ScrollProgress />
      <Hero />
      <Pipeline />
      <Marquee />
      <Features />
      <FinalCTA />
      <Footer />
      <FloatingCTA />
    </>
  );
}
