<script lang="ts">
  import Button from "../../components/Button.svelte";
  import { py } from "../../lib/bridge";
  import { t } from "../../lib/i18n.svelte";
  import { panelStats } from "../../lib/panel";
  import { app } from "../../lib/store.svelte";
  import { report } from "../../lib/toast.svelte";
  import Section from "./Section.svelte";

  let { index }: { index: number } = $props();
  let busy = $state(false);

  const platform = $derived(t(`about_platform_${app.platform}`));

  async function save() {
    busy = true;
    report(await py().diagnostics_export(panelStats()));
    busy = false;
  }

  async function openFolder() {
    report(await py().open_data_folder());
  }
</script>

<Section title={t("settings_about")} icon="shield" {index}>
  <p class="state mono">{t("about_version", { version: app.version, platform })}</p>
  <p class="hint">{t("about_hint")}</p>
  <div class="buttons">
    <Button size="sm" icon="folder" onclick={openFolder}>{t("about_open_folder")}</Button>
    <Button variant="accent" size="sm" icon="export" {busy} onclick={save}>{t("about_diagnostics")}</Button>
  </div>
</Section>
