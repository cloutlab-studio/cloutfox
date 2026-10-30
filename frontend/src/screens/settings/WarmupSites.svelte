<script lang="ts">
  import Field from "../../components/Field.svelte";
  import Select from "../../components/Select.svelte";
  import Textarea from "../../components/Textarea.svelte";
  import { t } from "../../lib/i18n.svelte";
  import { app, saveSettings } from "../../lib/store.svelte";
  import { toast } from "../../lib/toast.svelte";
  import Section from "./Section.svelte";

  let { index }: { index: number } = $props();
  let sites = $state(app.settings!.warmup_sites.join("\n"));
  const counts = $derived(
    [...new Set([...(app.options?.warmup_counts ?? [3, 5, 10, 15, 20, 30]), app.settings!.warmup_count])].sort((a, b) => a - b),
  );

  async function save() {
    const list = sites.split("\n").map((s) => s.trim()).filter(Boolean);
    if (list.join("\n") === app.settings!.warmup_sites.join("\n")) return;
    await saveSettings({ warmup_sites: list });
    sites = app.settings!.warmup_sites.join("\n");
    toast(t("warmup_sites_saved", { count: app.settings!.warmup_sites.length }), "ok");
  }
</script>

<Section title={t("settings_warmup")} icon="flame" {index}>
  <Field label={t("warmup_sites")} hint={t("warmup_sites_hint")}>
    <Textarea bind:value={sites} rows={7} mono onblur={save} />
  </Field>
  <Field label={t("warmup_count")}>
    <Select
      value={String(app.settings!.warmup_count)}
      options={counts.map((n) => ({ value: String(n), label: t("warmup_count_n", { n }) }))}
      onchange={(v) => saveSettings({ warmup_count: Number(v) })}
    />
  </Field>
</Section>
