import { CityCanvas } from "@/components/CityCanvas";
import { Sidebar } from "@/components/Sidebar";
import { DevPanel } from "@/components/DevPanel";
import { DiagramViewer } from "@/components/DiagramViewer";
import "@/styles/theme.css";

export function App() {
  return (
    <div className="app-layout">
      <CityCanvas />
      <Sidebar />
      <DevPanel />
      <DiagramViewer />
    </div>
  );
}
