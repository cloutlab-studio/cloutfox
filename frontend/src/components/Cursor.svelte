<script lang="ts">
  // The site's Brutal cursor: a square dot and a square ring with a hard shadow
  // that lags behind and turns yellow over anything you can press. Only with a
  // mouse, with motion on, and while Settings keep it on (data-cursor="on").
  let dot = $state<HTMLDivElement>();
  let ring = $state<HTMLDivElement>();
  let on = $state(false);
  let hover = $state(false);
  let down = $state(false);
  let hidden = $state(true);

  $effect(() => {
    const root = document.documentElement;
    const sync = () => (on = root.dataset.cursor === "on");
    sync();
    const watch = new MutationObserver(sync);
    watch.observe(root, { attributes: true, attributeFilter: ["data-cursor"] });

    let x = -100;
    let y = -100;
    let rx = x;
    let ry = y;
    // Frames run only while the ring catches up: an idle loop costs CPU.
    let frame = 0;
    const loop = () => {
      rx += (x - rx) * 0.22;
      ry += (y - ry) * 0.22;
      if (Math.abs(x - rx) < 0.1 && Math.abs(y - ry) < 0.1) {
        rx = x;
        ry = y;
      }
      if (dot) dot.style.transform = `translate(${x}px, ${y}px)`;
      if (ring) ring.style.transform = `translate(${rx}px, ${ry}px)`;
      frame = rx === x && ry === y ? 0 : requestAnimationFrame(loop);
    };
    const move = (e: PointerEvent) => {
      x = e.clientX;
      y = e.clientY;
      if (!frame && on) frame = requestAnimationFrame(loop);
      hidden = false;
      const target = e.target as Element | null;
      hover = Boolean(target?.closest?.("[data-press], button, a, label"));
    };
    const leave = () => (hidden = true);
    const press = () => (down = true);
    const release = () => (down = false);
    window.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", leave);
    window.addEventListener("pointerdown", press);
    window.addEventListener("pointerup", release);
    return () => {
      watch.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", leave);
      window.removeEventListener("pointerdown", press);
      window.removeEventListener("pointerup", release);
    };
  });
</script>

{#if on}
  <div class="ring" class:hover class:down class:hidden bind:this={ring} aria-hidden="true"><span></span></div>
  <div class="dot" class:hidden bind:this={dot} aria-hidden="true"></div>
{/if}

<style>
  .dot,
  .ring {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 1000;
    pointer-events: none;
  }
  .dot {
    width: 8px;
    height: 8px;
    margin: -4px 0 0 -4px;
    background: var(--t-fg);
    outline: 1.5px solid var(--t-bg);
  }
  .ring span {
    display: block;
    width: 30px;
    height: 30px;
    margin: -15px 0 0 -15px;
    border: 3px solid var(--t-fg);
    box-shadow: 4px 4px 0 var(--t-fg);
    transition:
      transform 0.3s var(--t-ease),
      background-color 0.15s linear,
      box-shadow 0.3s var(--t-ease);
  }
  .ring.hover span {
    background: rgb(255 225 77 / 0.55);
    transform: scale(1.35) rotate(45deg);
  }
  .ring.down span {
    transform: scale(0.8) rotate(45deg);
    box-shadow: 0 0 0 var(--t-fg);
  }
  .hidden {
    opacity: 0;
  }
</style>
