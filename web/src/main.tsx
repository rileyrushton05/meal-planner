import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import App from "./App.tsx";
import { createQueryClient } from "./api/queryClient";
import { CrashBoundary } from "./components/CrashBoundary";
import { initErrorTracking } from "./lib/monitoring";
import { redirectLegacyTabLink } from "./lib/location";

// Loads in the background when configured; nothing waits for it.
void initErrorTracking();

// Before anything reads the URL: links from when pages were tabs.
redirectLegacyTabLink();

const queryClient = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* A crash shows a way back instead of a blank page, and is reported. */}
    <CrashBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </CrashBoundary>
  </StrictMode>,
);
