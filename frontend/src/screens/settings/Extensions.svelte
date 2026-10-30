<script lang="ts">
  import Button from "../../components/Button.svelte";
  import IconButton from "../../components/IconButton.svelte";
  import Confirm from "../../dialogs/Confirm.svelte";
  import { py } from "../../lib/bridge";
  import { t } from "../../lib/i18n.svelte";
  import { open } from "../../lib/overlay.svelte";
  import { app, loadOptions } from "../../lib/store.svelte";
  import { report } from "../../lib/toast.svelte";
  import Section from "./Section.svelte";

  let { index }: { index: number } = $props();
  const list = $derived(app.options?.extensions ?? []);

  async function add(folder: boolean) {
    const result = await py().extension_add(folder);
    if (!result.cancelled) report(result);
    await loadOptions();
  }

  async function remove(id: string, name: string) {
    const ok = await open<boolean>(Confirm, {
      title: t("confirm_extension_remove", { name }),
      body: t("confirm_extension_body"),
    });
    if (!ok) return;
    report(await py().extension_remove(id));
    await loadOptions();
  }
</script>

<Section title={t("extensions")} icon="puzzle" {index}>
  <p class="hint">{t("extensions_hint")}</p>
  <ul class="list">
    {#each list as e (e.id)}
      <li>
        <span class="name">{e.name} <span class="dim">{e.version}</span></span>
        <span class="engine label">{e.engine === "chrome" ? "Chrome" : "Camoufox"}</span>
        <IconButton icon="trash" danger title={t("delete")} onclick={() => remove(e.id, e.name)} />
      </li>
    {:else}
      <li class="none dim">{t("extensions_none")}</li>
    {/each}
  </ul>
  <div class="buttons">
    <Button size="sm" icon="puzzle" onclick={() => add(false)}>{t("extension_add_file")}</Button>
    <Button size="sm" icon="folder" onclick={() => add(true)}>{t("extension_add_dir")}</Button>
  </div>
</Section>

<style>
  .list {
    margin: 0;
    padding: 0;
    list-style: none;
    border: 2px solid var(--t-line);
  }
  li {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 6px 6px 12px;
    border-bottom: 1px solid var(--t-bg-2);
  }
  li:last-child {
    border-bottom: 0;
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .engine {
    padding: 2px 6px;
    background: var(--t-bg-2);
  }
  .none {
    padding: 12px;
  }
</style>
