// The panel's sounds, synthesised with Web Audio: no sound files, no licences.
// Short and dry, in the spirit of the Brutal universe: square-ish clicks, a
// stamp thud, two-note rises and falls. The help chime is the old one (A5, E6).

export type Voice =
  | "tap"
  | "toggle"
  | "open"
  | "close"
  | "launch"
  | "live"
  | "stop"
  | "error"
  | "done"
  | "help";

// The shortest gap between two plays of one voice: a bulk launch of fifty
// profiles is one "live", not fifty.
export const GAPS: Record<Voice, number> = {
  tap: 40,
  toggle: 40,
  open: 120,
  close: 120,
  launch: 300,
  live: 600,
  stop: 600,
  error: 600,
  done: 900,
  help: 1500,
};

export class Limiter {
  private last = new Map<Voice, number>();

  allow(voice: Voice, now: number): boolean {
    const prev = this.last.get(voice);
    if (prev !== undefined && now - prev < GAPS[voice]) return false;
    this.last.set(voice, now);
    return true;
  }
}

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let noise: AudioBuffer | null = null;
let enabled = true;
let volume = 0.6;
const limiter = new Limiter();

export function configure(on: boolean, level: number): void {
  enabled = on;
  volume = Math.max(0, Math.min(1, level / 100));
  if (master) master.gain.value = volume;
}

function audio(): AudioContext | null {
  if (!ctx) {
    try {
      ctx = new AudioContext();
    } catch {
      return null;
    }
    master = ctx.createGain();
    master.gain.value = volume;
    // A gentle limiter so stacked voices never clip.
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -12;
    comp.ratio.value = 6;
    master.connect(comp).connect(ctx.destination);
    noise = ctx.createBuffer(1, ctx.sampleRate * 0.4, ctx.sampleRate);
    const data = noise.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

interface Tone {
  freq: number;
  to?: number;
  type?: OscillatorType;
  at?: number;
  dur: number;
  gain: number;
  attack?: number;
}

function tone(a: AudioContext, t0: number, { freq, to, type = "sine", at = 0, dur, gain, attack = 0.004 }: Tone) {
  const osc = a.createOscillator();
  const env = a.createGain();
  osc.type = type;
  const start = t0 + at;
  osc.frequency.setValueAtTime(freq, start);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, start + dur);
  env.gain.setValueAtTime(0, start);
  env.gain.linearRampToValueAtTime(gain, start + attack);
  env.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  osc.connect(env).connect(master!);
  osc.start(start);
  osc.stop(start + dur + 0.02);
}

function hiss(a: AudioContext, t0: number, { at = 0, dur, gain, from, to, q = 1.2 }: { at?: number; dur: number; gain: number; from: number; to: number; q?: number }) {
  const src = a.createBufferSource();
  src.buffer = noise;
  const filter = a.createBiquadFilter();
  filter.type = "bandpass";
  filter.Q.value = q;
  const start = t0 + at;
  filter.frequency.setValueAtTime(from, start);
  filter.frequency.exponentialRampToValueAtTime(to, start + dur);
  const env = a.createGain();
  env.gain.setValueAtTime(0, start);
  env.gain.linearRampToValueAtTime(gain, start + 0.01);
  env.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  src.connect(filter).connect(env).connect(master!);
  src.start(start);
  src.stop(start + dur + 0.02);
}

const VOICES: Record<Voice, (a: AudioContext, t: number) => void> = {
  // A dry key click: a square blip with a pitch drop.
  tap: (a, t) => tone(a, t, { freq: 1900, to: 900, type: "square", dur: 0.035, gain: 0.05 }),
  toggle: (a, t) => {
    tone(a, t, { freq: 1300, type: "square", dur: 0.03, gain: 0.045 });
    tone(a, t, { freq: 1950, type: "square", at: 0.045, dur: 0.03, gain: 0.04 });
  },
  // A sheet sliding in or out.
  open: (a, t) => hiss(a, t, { dur: 0.16, gain: 0.22, from: 700, to: 2600 }),
  close: (a, t) => hiss(a, t, { dur: 0.14, gain: 0.18, from: 2400, to: 600 }),
  launch: (a, t) => {
    tone(a, t, { freq: 523.25, type: "triangle", dur: 0.12, gain: 0.16 });
    tone(a, t, { freq: 783.99, type: "triangle", at: 0.08, dur: 0.18, gain: 0.16 });
  },
  // The rubber stamp: a low thud under a short paper slap.
  live: (a, t) => {
    tone(a, t, { freq: 150, to: 55, dur: 0.22, gain: 0.5, attack: 0.002 });
    hiss(a, t, { dur: 0.07, gain: 0.35, from: 3000, to: 1200, q: 0.7 });
    tone(a, t, { freq: 1046.5, type: "triangle", at: 0.09, dur: 0.22, gain: 0.08 });
  },
  stop: (a, t) => {
    tone(a, t, { freq: 659.25, type: "triangle", dur: 0.1, gain: 0.14 });
    tone(a, t, { freq: 392, type: "triangle", at: 0.08, dur: 0.2, gain: 0.14 });
  },
  error: (a, t) => {
    tone(a, t, { freq: 140, type: "sawtooth", dur: 0.11, gain: 0.12 });
    tone(a, t, { freq: 118, type: "sawtooth", at: 0.14, dur: 0.16, gain: 0.12 });
  },
  done: (a, t) => {
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) =>
      tone(a, t, { freq, type: "triangle", at: i * 0.07, dur: 0.24, gain: 0.12 }),
    );
  },
  // The help chime: two rising bell notes, distinct from system sounds.
  help: (a, t) => {
    tone(a, t, { freq: 880, dur: 0.5, gain: 0.35, attack: 0.01 });
    tone(a, t, { freq: 1760, dur: 0.25, gain: 0.05, attack: 0.01 });
    tone(a, t, { freq: 1318.5, at: 0.16, dur: 0.7, gain: 0.35, attack: 0.01 });
    tone(a, t, { freq: 2637, at: 0.16, dur: 0.3, gain: 0.05, attack: 0.01 });
  },
};

export function play(voice: Voice, force = false): void {
  if (!enabled && !force) return;
  if (!limiter.allow(voice, performance.now()) && !force) return;
  const a = audio();
  if (!a || !master) return;
  try {
    VOICES[voice](a, a.currentTime + 0.005);
  } catch {
    // Sound is decoration; never break a click over it.
  }
}
