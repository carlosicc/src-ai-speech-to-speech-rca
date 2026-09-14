import { HERO_RACKS } from "@/datacenter/config/layout";
import { CameraRig } from "@/datacenter/scene/CameraRig";
import { Facility } from "@/datacenter/scene/Facility";
import { HeroRack } from "@/datacenter/scene/HeroRack";
import { Interaction } from "@/datacenter/scene/Interaction";
import { NocWall } from "@/datacenter/scene/NocWall";
import { RackRows } from "@/datacenter/scene/RackRows";
import { ServiceLink } from "@/datacenter/scene/ServiceLink";

export function DataCenterScene() {
  return (
    <>
      <Facility />
      <RackRows />
      {HERO_RACKS.map((rack) => (
        <HeroRack key={rack.id} rack={rack} />
      ))}
      <ServiceLink />
      <NocWall />
      <CameraRig />
      <Interaction />
    </>
  );
}
