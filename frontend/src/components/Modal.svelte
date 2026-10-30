<script lang="ts">
  import type { Snippet } from "svelte";
  import IconButton from "./IconButton.svelte";
  import { t } from "../lib/i18n.svelte";

  // The sheet every dialog sits on: title, subtitle, body, actions.
  let {
    title,
    subtitle,
    width = 480,
    tone = "plain",
    onclose,
    children,
    actions,
  }: {
    title: string;
    subtitle?: string;
    width?: number;
    tone?: "plain" | "danger" | "alert";
    onclose?: () => void;
    children: Snippet;
    actions?: Snippet;
  } = $props();
</script>

<div class="sheet {tone}" style:--w="{width}px" role="dialog" aria-modal="true" aria-label={title}>
  <header>
    <div class="titles">
      <h2 class="display">{title}</h2>
      {#if subtitle}<p class="sub">{subtitle}</p>{/if}
    </div>
    {#if onclose}<IconButton icon="close" title={t("close_btn")} onclick={onclose} />{/if}
  </header>
  <div class="body">{@render children()}</div>
  {#if actions}<footer>{@render actions()}</footer>{/if}
</div>

<style>
  .sheet {
    width: min(var(--w), calc(100vw - 48px));
    max-height: calc(100vh - 64px);
    display: flex;
    flex-direction: column;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard-lg);
    animation: pop 0.42s var(--t-ease);
  }
  .danger {
    box-shadow: 10px 10px 0 var(--error);
  }
  .alert {
    box-shadow: 10px 10px 0 var(--t-accent-2);
  }
  header {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 20px 20px 14px 24px;
    border-bottom: var(--t-border-w) solid var(--t-line);
    background: var(--t-accent);
  }
  .danger header {
    background: var(--error);
    color: #fff;
  }
  .alert header {
    background: var(--t-accent-2);
  }
  .titles {
    flex: 1;
    min-width: 0;
  }
  h2 {
    margin: 0;
    font-size: 26px;
    overflow-wrap: anywhere;
  }
  .sub {
    margin: 6px 0 0;
    font-size: 13.5px;
    overflow-wrap: anywhere;
  }
  .body {
    display: grid;
    gap: 14px;
    padding: 20px 24px;
    overflow: auto;
  }
  footer {
    display: flex;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 12px;
    padding: 14px 24px 20px;
    border-top: 2px solid var(--t-bg-2);
  }
  @keyframes pop {
    from {
      opacity: 0;
      transform: translateY(24px) rotate(-1.5deg) scale(0.96);
    }
  }
</style>
