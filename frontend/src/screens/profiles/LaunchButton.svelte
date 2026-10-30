<script lang="ts">
  import Icon from "../../components/Icon.svelte";
  import type { Row } from "../../lib/bridge";
  import { t } from "../../lib/i18n.svelte";

  let { row, onclick }: { row: Row; onclick: () => void } = $props();
  const mode = $derived(row.loading ? "loading" : row.running ? "stop" : "launch");
</script>

<button type="button" class="launch {mode}" disabled={row.loading} data-press {onclick}>
  {#key mode}
    <span class="inner">
      {#if mode === "loading"}
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        {t("loading")}
      {:else if mode === "stop"}
        <Icon name="stop" size={13} />
        {t("stop")}
      {:else}
        <Icon name="play" size={14} />
        {t("launch")}
      {/if}
    </span>
  {/key}
</button>

<style>
  .launch {
    width: 120px;
    height: 34px;
    border: 2px solid var(--t-line);
    background: var(--t-accent);
    box-shadow: 3px 3px 0 var(--t-line);
    font: 600 11.5px/1 var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    overflow: hidden;
    transition:
      transform var(--t-dur) var(--t-ease),
      box-shadow var(--t-dur) var(--t-ease),
      background-color 0.12s linear;
  }
  .inner {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    animation: flip-in 0.35s var(--t-ease);
  }
  .launch:hover:not(:disabled) {
    background: var(--t-accent-2);
    transform: translate(-2px, -2px);
    box-shadow: 5px 5px 0 var(--t-line);
  }
  .launch:active:not(:disabled) {
    transform: translate(3px, 3px);
    box-shadow: none;
    transition-duration: 0.06s;
  }
  .stop {
    background: var(--t-fg);
    color: var(--t-bg);
  }
  .stop:hover:not(:disabled) {
    background: var(--live);
    color: #fff;
  }
  .loading {
    background: var(--t-surface);
    color: var(--t-muted);
    cursor: progress;
  }
  .dots {
    display: inline-flex;
    gap: 3px;
  }
  .dots i {
    width: 5px;
    height: 5px;
    background: currentColor;
    animation: hop 0.9s var(--t-ease) infinite;
    animation-play-state: var(--loops);
  }
  .dots i:nth-child(2) {
    animation-delay: 0.12s;
  }
  .dots i:nth-child(3) {
    animation-delay: 0.24s;
  }
  @keyframes hop {
    30% {
      transform: translateY(-5px);
    }
    60% {
      transform: none;
    }
  }
  @keyframes flip-in {
    from {
      transform: translateY(110%);
    }
  }
</style>
