import { Navigate, Route, Routes } from "react-router-dom";

import { Shell } from "./components/Shell";
import { DataProvider, useData } from "./lib/store";
import Agent from "./pages/Agent";
import Arrivals from "./pages/Arrivals";
import Automation from "./pages/Automation";
import Berths from "./pages/Berths";
import Documents from "./pages/Documents";
import Overview from "./pages/Overview";
import PortCallDetail from "./pages/PortCallDetail";
import PortCalls from "./pages/PortCalls";

function Gate({ children }: { children: React.ReactNode }) {
  const { loading, error, vessels, refresh } = useData();

  if (loading && vessels.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="relative h-9 w-9 overflow-hidden rounded-full border border-[color-mix(in_srgb,var(--color-starboard)_30%,transparent)]">
            <div className="sweep" />
          </div>
          <span className="label">Reading the operating day…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto flex h-full max-w-[560px] items-center justify-center">
        <div className="panel ticked w-full px-6 py-6">
          <div className="label mb-2">Cannot reach the services</div>
          <p className="mono text-[12px] leading-relaxed text-[var(--color-port)]">
            {error}
          </p>
          <p className="mt-3 text-[12px] leading-relaxed text-[var(--color-fog)]">
            Start both services, or clear{" "}
            <span className="mono">VITE_RESCHEDULING_API</span> and{" "}
            <span className="mono">VITE_PORT_OPS_API</span> to fall back to the
            bundled operating-day snapshot.
          </p>
          <button
            onClick={refresh}
            className="mono mt-4 cursor-pointer rounded-[3px] border border-[color-mix(in_srgb,var(--color-signal)_55%,transparent)] px-3 py-[7px] text-[10.5px] tracking-[0.12em] text-[var(--color-signal)] uppercase"
          >
            retry
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <DataProvider>
      <Shell>
        <Gate>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/arrivals" element={<Arrivals />} />
            <Route path="/berths" element={<Berths />} />
            <Route path="/agent" element={<Agent />} />
            <Route path="/port-calls" element={<PortCalls />} />
            <Route path="/port-calls/:id" element={<PortCallDetail />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/automation" element={<Automation />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Gate>
      </Shell>
    </DataProvider>
  );
}
