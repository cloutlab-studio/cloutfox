<script lang="ts">
  import type { Row } from "../lib/bridge";
  import { lastSeen } from "../lib/format";
  import { t } from "../lib/i18n.svelte";

  // State reads by form as well as ink: live is a rotated double-rule stamp in
  // blue, starting a dashed rule that runs, failure a struck red rule.
  let { row }: { row: Row } = $props();

  const state = $derived(
    row.failed && !row.loading && !row.running
      ? "failed"
      : row.loading
        ? "starting"
        : row.running
          ? "live"
          : "idle",
  );
  const seen = $derived(lastSeen(row.last.at));
</script>

{#key state}
  {#if state === "live"}
    <div class="stamp live" title={t("stamp_live")}>
      <span class="word">{t("stamp_live")}</span>
      {#if row.warmup}
        <span class="bar" style:--p={row.warmup.total ? row.warmup.done / row.warmup.total : 0}></span>
        <span class="small">{t("stamp_warmup", { done: row.warmup.done, total: row.warmup.total })}</span>
      {:else if row.since}
        <span class="small">{t("stamp_since", { time: row.since })}</span>
      {/if}
    </div>
  {:else if state === "starting"}
    <div class="stamp starting"><span class="word">{t("stamp_starting")}</span></div>
  {:else if state === "failed"}
    <div class="stamp failed" title={t("stamp_failed")}><span class="word">{t("stamp_failed")}</span></div>
  {:else}
    <div class="idle" title={seen ? t("last_launch_tooltip", { at: seen }) : undefined}>
      <span>{t("stamp_idle")}</span>
      {#if seen}<span class="small mono dim">{seen}</span>{/if}
    </div>
  {/if}
{/key}

<style>
  .stamp {
    display: inline-grid;
    justify-items: center;
    gap: 1px;
    min-width: 92px;
    padding: 3px 9px;
    font: 700 10.5px/1.25 var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .word {
    white-space: nowrap;
  }
  .small {
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 0.02em;
    text-transform: none;
    white-space: nowrap;
  }
  .live {
    position: relative;
    color: var(--live);
    border: 1.5px solid var(--live);
    background: rgb(255 255 255 / 0.5);
    transform: rotate(-4deg);
    animation: stamp 0.5s var(--t-ease) both;
  }
  /* The outer rule breathes by scale, which the compositor animates: a looping
     outline-offset would redraw the page on every frame. */
  .live::after {
    content: "";
    position: absolute;
    inset: -4.5px;
    border: 1px solid var(--live);
    pointer-events: none;
    animation: breathe 2.8s ease-in-out 0.6s infinite;
    animation-play-state: var(--loops);
  }
  .bar {
    width: 100%;
    height: 3px;
    margin: 2px 0 1px;
    background: linear-gradient(90deg, var(--live) calc(var(--p) * 100%), var(--live-tint) 0);
    transition: background 0.4s;
  }
  .starting {
    position: relative;
    overflow: hidden;
    color: var(--t-muted);
    border: 1.5px dashed var(--t-muted);
    padding: 4px 9px;
    border-top: 0;
    border-bottom: 0;
  }
  /* Dashed rules a dash wider on each side, moved by a dash: the top one right, the bottom one left. */
  .starting::before,
  .starting::after {
    content: "";
    position: absolute;
    left: -10px;
    width: calc(100% + 20px);
    height: 1.5px;
    background: linear-gradient(90deg, var(--t-muted) 50%, transparent 0) 0 0 / 10px 100% repeat-x;
    animation: ants 0.6s linear infinite;
    animation-play-state: var(--loops);
  }
  .starting::before {
    top: 0;
  }
  .starting::after {
    bottom: 0;
    animation-direction: reverse;
  }
  .failed {
    color: var(--error);
    border: 1.5px solid var(--error);
    transform: rotate(-4deg);
    padding: 5px 9px;
    text-decoration: line-through;
    text-decoration-thickness: 1px;
    animation:
      stamp 0.45s var(--t-ease) both,
      shake 0.45s 0.4s;
  }
  .idle {
    display: grid;
    gap: 1px;
    font-size: 13px;
    color: var(--dim);
  }
  @keyframes stamp {
    from {
      opacity: 0;
      transform: rotate(-16deg) scale(1.9);
    }
    60% {
      opacity: 1;
    }
  }
  @keyframes breathe {
    50% {
      transform: scale(1.03, 1.08);
    }
  }
  @keyframes ants {
    to {
      transform: translateX(10px);
    }
  }
</style>
