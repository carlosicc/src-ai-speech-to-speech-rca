import { CityCanvas } from "@/components/CityCanvas";
import { Sidebar } from "@/components/Sidebar";
import { DevPanel } from "@/components/DevPanel";
import { DiagramViewer } from "@/components/DiagramViewer";
import "@/styles/theme.css";

export function App() {
  return (
    <div className="app-layout">
      <div className="city-canvas-wrapper">
        <CityCanvas />
        <img src="/aws-logo.png" alt="AWS" className="aws-logo" />
        <div className="city-title">AI, You're On Call</div>
        <DiagramViewer />
      </div>
      <Sidebar />
      <DevPanel />
    </div>
  );
}
