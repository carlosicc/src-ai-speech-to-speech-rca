import { useEffect, useRef } from "react";
import { CityScene } from "@/engine/CityScene";
import { useSceneStore } from "@/store/sceneStore";

export function CityCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<CityScene | null>(null);
  const sceneState = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);

  useEffect(() => {
    const scene = new CityScene();
    sceneRef.current = scene;
    scene.init(containerRef.current!);
    return () => {
      scene.destroy();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    sceneRef.current?.transitionTo(sceneState, affectedService);
  }, [sceneState, affectedService]);

  return <div ref={containerRef} className="city-canvas" />;
}
