<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../components/Button.svelte";
  import Modal from "../components/Modal.svelte";
  import { py, type Activity } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";

  let { name, close }: { name: string; close: () => void } = $props();
  let entries = $state<Activity[] | null>(null);

  onMount(async () => {
    entries = await py().activity(name);
  });

  function params(p: Activity["params"]): string {
    if (typeof p === "string") return p;
    return Object.entries(p ?? {})
      .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
      .join(" ");
  }
</script>

<Modal title={t("menu_activity")} subtitle={name} width={760} onclose={close}>
  {#if entries && entries.length === 0}
    <p class="empty">{t("activity_empty")}</p>
  {:else if entries}
    <ol class="list mono selectable">
      {#each entries as e, i (i)}
        <li class:bad={!e.ok} style:animation-delay="{Math.min(i, 20) * 20}ms">
          <span class="at">{e.at.replace("T", " ").slice(5)}</span>
          <span class="act">{e.ok ? "" : "✗ "}{e.action}</span>
          <span class="params">{params(e.params)}{e.error ? ` · ${e.error}` : ""}</span>
        </li>
      {/each}
    </ol>
  {/if}
  {#snippet actions()}
    <Button onclick={close}>{t("close_btn")}</Button>
  {/snippet}
</Modal>

<style>
  .empty {
    margin: 0;
    color: var(--t-muted);
  }
  .list {
    margin: 0;
    padding: 0;
    list-style: none;
    max-height: 420px;
    overflow: auto;
    border: 2px solid var(--t-line);
    background: var(--rail);
    color: var(--rail-ink);
    font-size: 12px;
  }
  li {
    display: grid;
    grid-template-columns: 112px 130px 1fr;
    gap: 12px;
    padding: 6px 12px;
    border-bottom: 1px solid var(--rail-deep);
    animation: rise 0.3s var(--t-ease-out) backwards;
  }
  .at {
    color: var(--rail-muted);
  }
  .act {
    color: var(--t-accent);
    font-weight: 600;
  }
  .bad .act {
    color: #ff7a8c;
  }
  .params {
    overflow-wrap: anywhere;
  }
</style>
