<script lang="ts">
  import * as act from "../lib/actions";
  import { open, stack } from "../lib/overlay.svelte";
  import { app, selected } from "../lib/store.svelte";
  import Palette from "../dialogs/Palette.svelte";
  import Agents from "./Agents.svelte";
  import Log from "./Log.svelte";
  import Profiles from "./profiles/Profiles.svelte";
  import Rail from "./Rail.svelte";
  import Settings from "./settings/Settings.svelte";

  let search = $state<HTMLInputElement>();

  function palette() {
    if (!stack.some((e) => e.component === Palette)) void open(Palette);
  }

  function typing(e: KeyboardEvent): boolean {
    const el = e.target as HTMLElement;
    return el.isContentEditable || ["INPUT", "TEXTAREA"].includes(el.tagName);
  }

  function keydown(e: KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      palette();
      return;
    }
    if (typing(e) || stack.length || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "/") {
      e.preventDefault();
      app.page = "profiles";
      queueMicrotask(() => search?.focus());
    } else if (e.key === "n" || e.key === "т") {
      e.preventDefault();
      act.create();
    } else if (e.key === " " && selected.size === 1) {
      e.preventDefault();
      void act.launchOrStop([...selected][0]);
    }
  }
</script>

<svelte:window onkeydown={keydown} />

<div class="shell">
  <Rail onpalette={palette} />
  <main>
    {#key app.page}
      <div class="page">
        {#if app.page === "profiles"}
          <Profiles bind:search />
        {:else if app.page === "log"}
          <Log />
        {:else if app.page === "agents"}
          <Agents />
        {:else}
          <Settings />
        {/if}
      </div>
    {/key}
  </main>
</div>

<style>
  .shell {
    height: 100%;
    display: grid;
    grid-template-columns: auto 1fr;
  }
  main {
    position: relative;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }
  .page {
    height: 100%;
    animation: enter 0.45s var(--t-ease);
  }
  @keyframes enter {
    from {
      opacity: 0;
      transform: translateX(24px);
    }
  }
</style>
