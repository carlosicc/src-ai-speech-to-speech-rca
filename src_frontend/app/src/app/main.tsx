import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { App } from "./App";
// Register the link-store WebSocket handler eagerly so the connect-time system_status is not
// missed while the lazy /datacenter chunk is still loading.
import "@/store/infrastructureStore";

const DataCenterPage = lazy(() =>
  import("@/datacenter/DataCenterPage").then((m) => ({ default: m.DataCenterPage })),
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route
          path="/datacenter"
          element={
            <Suspense fallback={<div style={{ color: "#fff", padding: 24 }}>Loading data center…</div>}>
              <DataCenterPage />
            </Suspense>
          }
        />
        <Route path="*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
