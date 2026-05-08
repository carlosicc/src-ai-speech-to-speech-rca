import {
  ROOMS,
  ROOM_HEIGHT,
  FLOOR_GAP,
  BUILDING_WIDTH,
  SCALE,
  NPC_SHEETS,
  NPC_FRAME_SIZE,
  PIXELSPACES_NPC_COUNT,
  CHARACTERS,
} from "@/engine/config";
import type { SceneState } from "@/types/scene";
import { getRoomOverlay, getCharacterBehavior } from "@/engine/effects";

type CharAnimState = "walk" | "idle" | "panic";

interface Character {
  x: number;
  y: number;
  tx: number;
  ty: number;
  speed: number;
  room: number;
  animState: CharAnimState;
  facingLeft: boolean;
  frame: number;
  frameTimer: number;
  sheetIndex: number;
  waitTimer: number;
}

export class CityScene {
  private canvas!: HTMLCanvasElement;
  private ctx!: CanvasRenderingContext2D;
  private container!: HTMLElement;
  private W = 0;
  private H = 0;
  private time = 0;
  private animId = 0;
  private resizeHandler: (() => void) | null = null;
  private npcSheets: HTMLImageElement[] = [];
  private furnitureImages = new Map<string, HTMLImageElement>();
  private bgImages = new Map<string, HTMLImageElement>();
  private spritesLoaded = false;
  private characters: Character[] = [];
  private currentState: SceneState = "HEALTHY";
  private affectedRoom: string | null = null;

  async init(container: HTMLElement): Promise<void> {
    this.container = container;
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d")!;
    this.ctx.imageSmoothingEnabled = false;

    this.resize();
    this.resizeHandler = () => this.resize();
    window.addEventListener("resize", this.resizeHandler);

    this.initCharacters();
    await this.loadAssets();

    this.animId = requestAnimationFrame(() => this.loop());
  }

  private async loadAssets(): Promise<void> {
    const load = (src: string): Promise<HTMLImageElement> =>
      new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(img);
        img.src = src;
      });

    // Load NPC sheets
    this.npcSheets = await Promise.all(NPC_SHEETS.map(load));

    // Collect all furniture sprites needed
    const furnitureSet = new Set<string>();
    for (const room of ROOMS) {
      for (const f of room.furniture) {
        furnitureSet.add(f.sprite);
      }
    }

    // Load furniture
    const furniturePromises = [...furnitureSet].map(async (name) => {
      const img = await load(`/sprites/furniture/${name}`);
      this.furnitureImages.set(name, img);
    });

    // Load background pieces
    const bgNames = ["Mountain_large_1.png", "Mountain_medium_1.png", "Cloud_1.png", "Cloud_small_3.png", "Tree_medium.png", "House_largel_red.png", "House_small_beige.png"];
    const bgPromises = bgNames.map(async (name) => {
      const img = await load(`/sprites/bg/${name}`);
      this.bgImages.set(name, img);
    });

    await Promise.all([...furniturePromises, ...bgPromises]);
    this.spritesLoaded = true;
  }

  private resize(): void {
    const dpr = window.devicePixelRatio || 1;
    this.W = this.container.clientWidth;
    this.H = this.container.clientHeight;
    this.canvas.width = this.W * dpr;
    this.canvas.height = this.H * dpr;
    this.canvas.style.width = this.W + "px";
    this.canvas.style.height = this.H + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.ctx.imageSmoothingEnabled = false;
  }

  private initCharacters(): void {
    for (let i = 0; i < CHARACTERS.length; i++) {
      const room = i % ROOMS.length;
      const roomCfg = ROOMS[room];
      const startX = roomCfg.x + 20 + Math.random() * (roomCfg.width - 40);
      this.characters.push({
        x: startX,
        y: 0,
        tx: startX,
        ty: 0,
        speed: CHARACTERS[i].speed,
        room,
        animState: "walk",
        facingLeft: Math.random() > 0.5,
        frame: 0,
        frameTimer: 0,
        sheetIndex: i % NPC_SHEETS.length,
        waitTimer: Math.random() * 60,
      });
    }
  }

  private getRoomY(floor: number): number {
    // Floor 2 = top, floor 0 = bottom
    const totalHeight = 3 * ROOM_HEIGHT + 2 * FLOOR_GAP;
    const buildingTop = (this.H / SCALE - totalHeight) / 2 + 20;
    return buildingTop + (2 - floor) * (ROOM_HEIGHT + FLOOR_GAP);
  }

  private loop(): void {
    this.time++;
    this.draw();
    this.animId = requestAnimationFrame(() => this.loop());
  }

  private draw(): void {
    const { ctx, W, H } = this;
    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(0, 0, W, H);

    ctx.save();
    ctx.scale(SCALE, SCALE);

    this.drawBackground();
    this.drawBuilding();
    this.updateCharacters();
    this.drawCharacters();

    ctx.restore();
  }

  private drawBackground(): void {
    if (!this.spritesLoaded) return;
    const { ctx } = this;
    const sw = this.W / SCALE;
    const sh = this.H / SCALE;

    // Sky gradient
    ctx.fillStyle = "#16213e";
    ctx.fillRect(0, 0, sw, sh * 0.5);
    ctx.fillStyle = "#0f3460";
    ctx.fillRect(0, sh * 0.5, sw, sh * 0.5);

    // Mountains in background
    const mtnLarge = this.bgImages.get("Mountain_large_1.png");
    const mtnMed = this.bgImages.get("Mountain_medium_1.png");
    if (mtnLarge) {
      ctx.globalAlpha = 0.3;
      ctx.drawImage(mtnLarge, sw - 200, sh * 0.35);
      ctx.drawImage(mtnLarge, sw - 380, sh * 0.38);
      ctx.globalAlpha = 1;
    }
    if (mtnMed) {
      ctx.globalAlpha = 0.2;
      ctx.drawImage(mtnMed, 10, sh * 0.4);
      ctx.globalAlpha = 1;
    }

    // Clouds
    const cloud = this.bgImages.get("Cloud_1.png");
    const cloudSmall = this.bgImages.get("Cloud_small_3.png");
    if (cloud) {
      const cx = ((this.time * 0.05) % (sw + 60)) - 30;
      ctx.globalAlpha = 0.5;
      ctx.drawImage(cloud, cx, 20);
      ctx.drawImage(cloud, cx + sw * 0.4, 35);
      ctx.globalAlpha = 1;
    }
    if (cloudSmall) {
      const cx2 = ((this.time * 0.03 + 100) % (sw + 40)) - 20;
      ctx.globalAlpha = 0.4;
      ctx.drawImage(cloudSmall, cx2, 15);
      ctx.globalAlpha = 1;
    }

    // Ground
    ctx.fillStyle = "#2d4a22";
    ctx.fillRect(0, sh - 20, sw, 20);

    // Trees
    const tree = this.bgImages.get("Tree_medium.png");
    if (tree) {
      ctx.drawImage(tree, 5, sh - 60);
      ctx.drawImage(tree, sw - 50, sh - 55);
    }
  }

  private drawBuilding(): void {
    const { ctx } = this;
    const sw = this.W / SCALE;

    // Building frame
    const bx = (sw - BUILDING_WIDTH) / 2;

    for (const room of ROOMS) {
      const ry = this.getRoomY(room.floor);
      const rx = bx + room.x;

      // Room background
      ctx.fillStyle = room.color;
      ctx.fillRect(rx, ry, room.width, ROOM_HEIGHT);

      // Room border
      ctx.strokeStyle = "#3a4a6a";
      ctx.lineWidth = 1;
      ctx.strokeRect(rx, ry, room.width, ROOM_HEIGHT);

      // Floor line
      ctx.strokeStyle = "#4a5a7a";
      ctx.beginPath();
      ctx.moveTo(rx, ry + ROOM_HEIGHT);
      ctx.lineTo(rx + room.width, ry + ROOM_HEIGHT);
      ctx.stroke();

      // Furniture
      if (this.spritesLoaded) {
        for (const f of room.furniture) {
          const img = this.furnitureImages.get(f.sprite);
          if (img && img.naturalWidth > 0) {
            ctx.drawImage(img, rx + f.xOffset, ry + f.yOffset);
          }
        }
      }

      // Room label (inside room, top-left)
      ctx.fillStyle = "rgba(200, 220, 240, 0.8)";
      ctx.font = "bold 6px monospace";
      ctx.textAlign = "left";
      ctx.fillText(room.label, rx + 5, ry + 12);

      // Room effect overlay
      const overlay = getRoomOverlay(room.id, this.affectedRoom, this.currentState, this.time);
      if (overlay) {
        ctx.fillStyle = overlay.color;
        ctx.globalAlpha = overlay.alpha;
        ctx.fillRect(rx, ry, room.width, ROOM_HEIGHT);
        ctx.globalAlpha = 1;
      }
    }
  }

  private updateCharacters(): void {
    for (const ch of this.characters) {
      const roomCfg = ROOMS[ch.room];
      const behavior = getCharacterBehavior(roomCfg.id, this.affectedRoom, this.currentState);
      ch.animState = behavior;

      ch.frameTimer++;
      const speed = ch.animState === "panic" ? 4 : 10;
      if (ch.frameTimer >= speed) {
        ch.frameTimer = 0;
        ch.frame = (ch.frame + 1) % 4;
      }

      if (ch.animState === "idle") {
        ch.waitTimer = 10;
        continue;
      }

      if (ch.waitTimer > 0) {
        ch.waitTimer--;
        continue;
      }

      const dx = ch.tx - ch.x;

      if (Math.abs(dx) < 1) {
        ch.waitTimer = ch.animState === "panic" ? 10 + Math.random() * 20 : 40 + Math.random() * 80;
        ch.tx = roomCfg.x + 10 + Math.random() * (roomCfg.width - 20);
      } else {
        const moveSpeed = ch.animState === "panic" ? ch.speed * 2.5 : ch.speed;
        ch.x += Math.sign(dx) * moveSpeed;
        ch.facingLeft = dx < 0;
      }
    }
  }

  private drawCharacters(): void {
    if (!this.spritesLoaded) return;
    const { ctx } = this;
    const sw = this.W / SCALE;
    const bx = (sw - BUILDING_WIDTH) / 2;

    for (const ch of this.characters) {
      const sheet = this.npcSheets[ch.sheetIndex];
      if (!sheet || sheet.naturalWidth === 0) continue;

      const roomCfg = ROOMS[ch.room];
      const ry = this.getRoomY(roomCfg.floor);
      const cx = bx + ch.x;
      const cy = ry + ROOM_HEIGHT - NPC_FRAME_SIZE;

      const isPixelSpaces = ch.sheetIndex < PIXELSPACES_NPC_COUNT;

      let sx: number, sy: number;

      if (isPixelSpaces) {
        // PixelSpaces layout: 64x48, row 0=front(4fr), row 1=side(3fr), row 2=back(2fr)
        if (ch.animState === "idle") {
          sx = 0;
          sy = 0;
        } else {
          // Use side walk row (row 1), 3 frames
          sx = (ch.frame % 3) * NPC_FRAME_SIZE;
          sy = NPC_FRAME_SIZE;
        }
      } else {
        // OldTown layout: 64x496, rows in groups
        // Walk side = rows 6-7, 4 frames each
        // Idle down = rows 0-1
        if (ch.animState === "idle") {
          sx = (ch.frame % 4) * NPC_FRAME_SIZE;
          sy = 0;
        } else {
          sx = (ch.frame % 4) * NPC_FRAME_SIZE;
          sy = 6 * NPC_FRAME_SIZE; // walk side row
        }
      }

      ctx.save();
      if (ch.facingLeft) {
        ctx.translate(cx + NPC_FRAME_SIZE / 2, cy);
        ctx.scale(-1, 1);
        ctx.drawImage(sheet, sx, sy, NPC_FRAME_SIZE, NPC_FRAME_SIZE, -NPC_FRAME_SIZE / 2, 0, NPC_FRAME_SIZE, NPC_FRAME_SIZE);
      } else {
        ctx.drawImage(sheet, sx, sy, NPC_FRAME_SIZE, NPC_FRAME_SIZE, cx, cy, NPC_FRAME_SIZE, NPC_FRAME_SIZE);
      }
      ctx.restore();
    }
  }

  transitionTo(state: SceneState, affectedRoom: string | null = null): void {
    this.currentState = state;
    this.affectedRoom = affectedRoom;
  }

  destroy(): void {
    if (this.resizeHandler) {
      window.removeEventListener("resize", this.resizeHandler);
    }
    cancelAnimationFrame(this.animId);
    this.canvas.remove();
  }
}
