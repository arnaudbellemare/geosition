import { SovereignDashboard } from "@/components/sovereign-dashboard";

export const metadata = {
  title: "GEO/AEO Tracker — Demo",
  description: "Read-only demo of the GEO/AEO Tracker. Explore AI visibility tracking, competitor battlecards, citation analysis, and more.",
};

export default function DemoPage() {
  return <SovereignDashboard demoMode />;
}
