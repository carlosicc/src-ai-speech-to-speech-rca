import { Suspense, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { ACESFilmicToneMapping } from "three";
import { DevPanel } from "@/components/DevPanel";
import { Hud } from "@/datacenter/hud/Hud";
import { DataCenterScene } from "@/datacenter/scene/DataCenterScene";
import "@/styles/theme.css";
import "@/datacenter/datacenter.css";

function hasWebGl(): boolean {
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function DataCenterPage() {
  const supported = useMemo(hasWebGl, []);

  if (!supported) {
    return (
      <div className="dc-unsupported">
        <h1>3D view unavailable</h1>
        <p>This browser has no WebGL support.</p>
        <a href="/">Open the classic operations view</a>
      </div>
    );
  }

  return (
    <div className="dc-root">
      <Canvas
        dpr={[1, 1.5]}
        camera={{ fov: 60, near: 0.1, far: 120, position: [0, 3.8, 13] }}
        gl={{ antialias: true }}
        onCreated={({ gl }) => {
          gl.toneMapping = ACESFilmicToneMapping;
        }}
      >
        <Suspense fallback={null}>
          <DataCenterScene />
        </Suspense>
      </Canvas>
      <Hud />
      <DevPanel />
    </div>
  );
}
