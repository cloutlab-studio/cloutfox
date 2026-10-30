<script lang="ts">
  import Switch from "../../components/Switch.svelte";
  import { t } from "../../lib/i18n.svelte";
  import { app, saveSettings } from "../../lib/store.svelte";
  import Section from "./Section.svelte";

  let { index }: { index: number } = $props();
</script>

<Section title={t("settings_launch")} icon="shield" {index}>
  <Switch checked={app.settings!.geo_guard} label={t("geo_guard")} onchange={(v) => saveSettings({ geo_guard: v })} />
  <p class="hint">{t("geo_guard_hint")}</p>
</Section>
