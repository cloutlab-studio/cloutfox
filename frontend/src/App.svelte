<script lang="ts">
  import { onMount } from "svelte";
  import Cursor from "./components/Cursor.svelte";
  import OverlayHost from "./components/OverlayHost.svelte";
  import Toasts from "./components/Toasts.svelte";
  import { init } from "./lib/bridge";
  import { collectGarbage } from "./lib/gc";
  import { setStrings } from "./lib/i18n.svelte";
  import { onSystemMotion, watchFocus } from "./lib/motion";
  import { closeTop } from "./lib/overlay.svelte";
  import { app, applySettings, opened } from "./lib/store.svelte";
  import Lock from "./screens/Lock.svelte";
  import Shell from "./screens/Shell.svelte";
  import Help from "./screens/Help.svelte";

  onMount(async () => {
    watchFocus();
    collectGarbage();
    const api = await init();
    const boot = await api.boot();
    setStrings(boot.language, boot.strings);
    applySettings(boot.settings);
    app.version = boot.version;
    onSystemMotion(() => app.settings && applySettings(app.settings));
    if (boot.locked) {
      app.phase = "lock";
    } else {
      await api.start();
      await opened();
    }
  });

  function keydown(e: KeyboardEvent) {
    if (e.key === "Escape" && closeTop()) e.preventDefault();
  }
</script>

<svelte:window onkeydown={keydown} />

{#if app.phase === "lock"}
  <Lock />
{:else if app.phase === "open"}
  <Shell />
  <Help />
{:else}
  <div class="boot" aria-busy="true"><span class="display">CloutFox</span></div>
{/if}

<OverlayHost />
<Toasts />
<Cursor />

<style>
  .boot {
    height: 100%;
    display: grid;
    place-items: center;
    background: var(--rail);
    color: var(--rail-ink);
  }
  .boot span {
    font-size: 64px;
    animation: blink 1s steps(1) infinite;
    animation-play-state: var(--loops);
  }
</style>
