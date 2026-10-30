<script lang="ts" module>
  // Drawn for the panel: 24px grid, thick square strokes to match the 2px and
  // 3px rules. Paths only; colour comes from currentColor.
  export const ICONS = {
    play: "M7 4.5v15l12-7.5z",
    stop: "M6 6h12v12H6z",
    plus: "M12 4v16M4 12h16",
    layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
    import: "M12 3v12M7 10l5 5 5-5M4 20h16",
    export: "M12 15V3M7 8l5-5 5 5M4 20h16",
    search: "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM15.5 15.5L21 21",
    cog: "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
    log: "M4 5h16M4 10h16M4 15h10M4 20h7",
    bot: "M5 8h14v11H5zM12 4v4M9 13h.01M15 13h.01M9 16.5h6M2 12v4M22 12v4",
    users: "M3 4h8v8H3zM13 12h8v8h-8zM13 4h8v5h-8zM3 15h8v5H3z",
    cookie: "M20.5 12A8.5 8.5 0 1 1 12 3.5a3 3 0 0 0 4 3 3 3 0 0 0 4.5 5.5zM8.5 9.5h.01M8 15h.01M13 13.5h.01M15.5 17h.01",
    edit: "M4 20h4l11-11-4-4L4 16zM13.5 6.5l4 4",
    trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6",
    more: "M12 5h.01M12 12h.01M12 19h.01",
    close: "M5 5l14 14M19 5L5 19",
    check: "M4 12.5l5 5L20 6.5",
    lock: "M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3",
    unlock: "M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 6.8-1.2",
    key: "M8 10.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM10.8 11.7L19 3.5M16 6.5l2.5 2.5M14 8.5l2 2",
    flame: "M12 21c-4 0-7-2.7-7-6.5 0-3 2-5.2 3.5-6.8.3 2 1.3 3.1 2.5 3.6C10.5 7.6 12 4.6 15 3c-.5 3 1 4.6 2.5 6.5 1 1.3 1.5 2.8 1.5 4.5 0 4-3 7-7 7z",
    copy: "M8 8h12v12H8zM16 8V4H4v12h4",
    globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.4 3.6 5.5 3.6 9s-1.1 6.6-3.6 9M12 3C9.5 5.4 8.4 8.5 8.4 12s1.1 6.6 3.6 9",
    wifi: "M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.5 16a5 5 0 0 1 7 0M12 19.5h.01",
    tunnel: "M3 20V11a9 9 0 0 1 18 0v9M7.5 20v-8.5a4.5 4.5 0 0 1 9 0V20M3 20h18",
    refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
    chevron: "M9 6l6 6-6 6",
    down: "M6 9l6 6 6-6",
    folder: "M3 6h7l2 2.5h9V19H3z",
    file: "M6 3h8l5 5v13H6zM14 3v5h5",
    volume: "M4 9h4l5-4v14l-5-4H4zM16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12",
    mute: "M4 9h4l5-4v14l-5-4H4zM16 9.5l5 5M21 9.5l-5 5",
    fingerprint: "M7 18.5c1-1.8 1.5-4 1.5-6.5a3.5 3.5 0 0 1 7 0c0 1.5-.1 2.9-.4 4.2M12 12c0 3.4-.8 6.3-2.3 8.5M5 15.5c.3-1.1.5-2.3.5-3.5a6.5 6.5 0 0 1 11.6-4M18.3 10.5c.1.5.2 1 .2 1.5 0 2.6-.4 5-1.2 7M4 9.5A9 9 0 0 1 15.5 3.7",
    eye: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
    bolt: "M13 2.5L5 13.5h6l-1 8 8-11h-6z",
    shield: "M12 3l8 3v6c0 4.5-3.3 8-8 9.5C7.3 20 4 16.5 4 12V6z",
    puzzle: "M4 8h4a2 2 0 1 1 4 0h4v4a2 2 0 1 1 0 4v4H4z",
    archive: "M3 4h18v4H3zM5 8v12h14V8M10 12h4",
    command: "M8 4a2 2 0 1 0 0 4h2V6a2 2 0 0 0-2-2zM16 4a2 2 0 0 1 0 4h-2V6a2 2 0 0 1 2-2zM8 20a2 2 0 1 1 0-4h2v2a2 2 0 0 1-2 2zM16 20a2 2 0 1 0 0-4h-2v2a2 2 0 0 0 2 2zM10 8h4v8h-4z",
    hand: "M8 12V5a1.5 1.5 0 0 1 3 0v6M11 10V3.5a1.5 1.5 0 0 1 3 0V10M14 10V5a1.5 1.5 0 0 1 3 0v8c0 4.5-2.5 8-7 8-3 0-4.5-1.5-6-4l-2-3.5a1.5 1.5 0 0 1 2.5-1.5L8 15",
    sparkle: "M12 3l1.8 5.7L19.5 10.5l-5.7 1.8L12 18l-1.8-5.7L4.5 10.5l5.7-1.8z",
  } as const;

  export type IconName = keyof typeof ICONS;
</script>

<script lang="ts">
  let { name, size = 18, stroke = 2.4 }: { name: IconName; size?: number; stroke?: number } = $props();
  const filled = $derived(name === "play" || name === "stop" || name === "bolt");
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill={filled ? "currentColor" : "none"}
  stroke="currentColor"
  stroke-width={filled ? 0 : stroke}
  stroke-linecap="square"
  stroke-linejoin="miter"
  aria-hidden="true"
  class="icon"
>
  <path d={ICONS[name]} />
</svg>

<style>
  .icon {
    flex: none;
    display: block;
  }
</style>
