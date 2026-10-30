<script lang="ts">
  import { t } from "../../lib/i18n.svelte";
  import { app, isLive } from "../../lib/store.svelte";

  // A running strip of what is live right now; it holds still on hover.
  const live = $derived(app.rows.filter(isLive));
  const items = $derived(
    live.length
      ? live.map((r) =>
          r.warmup
            ? { name: r.name, text: t("stamp_warmup", { done: r.warmup.done, total: r.warmup.total }) }
            : { name: r.name, text: `${t("stamp_live")}${r.since ? ` ${t("stamp_since", { time: r.since })}` : ""}` },
        )
      : [t("ticker_idle"), t("ticker_api"), t("ticker_hotkeys")].map((text) => ({ name: "", text })),
  );
  // Long enough to fill the strip twice for a seamless loop.
  const loop = $derived(Array.from({ length: Math.max(2, Math.ceil(8 / items.length)) }, () => items).flat());
</script>

<div class="ticker" class:on={live.length > 0} aria-hidden="true">
  <div class="track" style:--speed="{Math.max(24, loop.length * 4)}s">
    {#each [0, 1] as half (half)}
      <span class="half">
        {#each loop as item, i (i)}<span class="item">{#if item.name}<i class="dot"></i><b class="name">{item.name}</b>{" · "}{/if}{item.text}</span><span class="sep">✦</span>{/each}
      </span>
    {/each}
  </div>
</div>

<style>
  .ticker {
    margin: 0 -32px;
    height: 34px;
    overflow: hidden;
    border-bottom: var(--t-border-w) solid var(--t-line);
    background: var(--t-fg);
    color: var(--rail-muted);
    font: 600 11.5px/34px var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    white-space: nowrap;
  }
  .ticker.on {
    background: var(--t-accent);
    color: var(--t-fg);
  }
  .track {
    display: flex;
    width: max-content;
    animation: marquee var(--speed) linear infinite;
    animation-play-state: var(--loops);
  }
  .ticker:hover .track {
    animation-play-state: paused;
  }
  .item {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .sep {
    padding: 0 18px;
  }
  /* Profile names keep their case. */
  .name {
    text-transform: none;
    letter-spacing: 0.02em;
  }
  .dot {
    width: 8px;
    height: 8px;
    background: var(--live);
    animation: blink 1.2s steps(1) infinite;
    animation-play-state: var(--loops);
  }
</style>
