<script lang="ts">
  import { untrack } from "svelte";
  import Button from "../components/Button.svelte";
  import Checkbox from "../components/Checkbox.svelte";
  import Modal from "../components/Modal.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { app } from "../lib/store.svelte";
  import { toast } from "../lib/toast.svelte";

  let { preset = [], close }: { preset?: string[]; close: () => void } = $props();

  const names = app.rows.map((r) => r.name);
  let chosen = $state(untrack(() => new Set<string>(preset.length ? preset : names)));
  let withData = $state(true);
  let busy = $state(false);
  const all = $derived(chosen.size === names.length);

  function flip(name: string, on: boolean) {
    const next = new Set(chosen);
    if (on) next.add(name);
    else next.delete(name);
    chosen = next;
  }

  async function go() {
    busy = true;
    const result = await py().export_profiles([...chosen], withData);
    busy = false;
    if (result.cancelled) return;
    toast(`${t("export_success")}: ${result.exported} → ${result.folder}`, "ok");
    close();
  }
</script>

<Modal title={t("export_profiles")} subtitle={t("choose_profiles_to_export")} width={520} onclose={close}>
  <div class="head">
    <Checkbox
      checked={all}
      indeterminate={!all && chosen.size > 0}
      label={t("select_all")}
      onchange={(v) => (chosen = new Set(v ? names : []))}
    />
    <span class="mono dim">{chosen.size}/{names.length}</span>
  </div>
  <div class="list">
    {#each names as name (name)}
      <Checkbox checked={chosen.has(name)} label={name} onchange={(v) => flip(name, v)} />
    {/each}
  </div>
  <Checkbox bind:checked={withData} label={t("include_browser_data")} />
  {#snippet actions()}
    <Button variant="ghost" onclick={close}>{t("cancel")}</Button>
    <Button variant="accent" icon="export" {busy} disabled={chosen.size === 0} onclick={go}>{t("export")}</Button>
  {/snippet}
</Modal>

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--t-line);
  }
  .list {
    display: grid;
    gap: 8px;
    max-height: 300px;
    overflow: auto;
    padding: 2px 4px 6px 2px;
  }
</style>
