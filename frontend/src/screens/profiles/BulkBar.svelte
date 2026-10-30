<script lang="ts">
  import { fly } from "svelte/transition";
  import Button from "../../components/Button.svelte";
  import Counter from "../../components/Counter.svelte";
  import * as act from "../../lib/actions";
  import { t } from "../../lib/i18n.svelte";
  import { selected } from "../../lib/store.svelte";

  const names = $derived([...selected]);
</script>

{#if selected.size > 0}
  <div class="bar" transition:fly={{ y: 120, duration: 420, opacity: 1 }}>
    <span class="count display"><Counter value={selected.size} /></span>
    <span class="label">{t("selected_short")}</span>
    <span class="grow"></span>
    <Button variant="accent" size="sm" icon="play" onclick={() => act.launchMany(names)}>{t("launch")}</Button>
    <Button size="sm" icon="stop" onclick={() => act.stopMany(names)}>{t("stop")}</Button>
    <Button size="sm" icon="flame" onclick={() => act.warmup(names)}>{t("bulk_warmup")}</Button>
    <Button size="sm" icon="edit" onclick={() => act.bulkEdit(names)}>{t("bulk_edit_btn")}</Button>
    <Button size="sm" icon="export" onclick={() => act.exportProfiles(names)}>{t("export")}</Button>
    <Button size="sm" variant="danger" icon="trash" onclick={() => act.remove(names)}>{t("delete")}</Button>
    <Button size="sm" variant="ghost" icon="close" onclick={() => selected.clear()}>{t("clear")}</Button>
  </div>
{/if}

<style>
  .bar {
    position: absolute;
    left: 50%;
    bottom: 40px;
    translate: -50% 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px 10px 18px;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-fg);
    color: var(--t-bg);
    box-shadow: 8px 8px 0 var(--t-accent);
    white-space: nowrap;
  }
  .count {
    font-size: 30px;
    color: var(--t-accent);
  }
  .label {
    color: var(--rail-muted);
  }
  .grow {
    width: 12px;
  }
  .bar :global(.ghost) {
    color: var(--t-bg);
  }
</style>
