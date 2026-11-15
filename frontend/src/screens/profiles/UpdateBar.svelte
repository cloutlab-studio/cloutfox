<script lang="ts">
  import Button from "../../components/Button.svelte";
  import Icon from "../../components/Icon.svelte";
  import { py } from "../../lib/bridge";
  import { t } from "../../lib/i18n.svelte";
  import { app, refresh } from "../../lib/store.svelte";
  import { report } from "../../lib/toast.svelte";

  let busy = $state(false);
  const update = $derived(app.update);

  async function install() {
    busy = true;
    report(await py().update_install());
    busy = false;
    void refresh();
  }

  async function later() {
    await py().update_dismiss(update?.latest);
    void refresh();
  }
</script>

{#if update?.available && !update.skipped}
  <div class="bar" role="status">
    <Icon name="bolt" size={16} />
    <span class="text">{t("update_available", { version: update.latest })}</span>
    <Button size="sm" variant="accent" icon="import" {busy} onclick={install}>
      {t("update_install")}
    </Button>
    <Button size="sm" icon="export" onclick={() => py().open_external(update.url)}>
      {t("update_open")}
    </Button>
    <button type="button" class="x" title={t("update_later")} onclick={later}>×</button>
  </div>
{/if}

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 0 32px 4px;
    padding: 8px 12px;
    border: 2px solid var(--t-line);
    background: var(--t-accent);
    color: var(--t-fg);
    box-shadow: 4px 4px 0 var(--t-accent-2);
    animation: rise 0.35s var(--t-ease);
  }
  .text {
    flex: 1;
    font: 600 13px var(--font-mono);
  }
  .x {
    padding: 0 4px;
    border: 0;
    background: none;
    color: inherit;
    font-size: 20px;
    line-height: 1;
  }
  .x:hover {
    color: var(--error);
  }
</style>
