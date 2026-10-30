<script lang="ts">
  import Button from "../../components/Button.svelte";
  import Field from "../../components/Field.svelte";
  import Select from "../../components/Select.svelte";
  import { py } from "../../lib/bridge";
  import { t } from "../../lib/i18n.svelte";
  import { app, applySettings, saveSettings } from "../../lib/store.svelte";
  import { report } from "../../lib/toast.svelte";
  import Section from "./Section.svelte";

  let { index }: { index: number } = $props();
  const s = $derived(app.settings!);
  let busy = $state(false);

  async function choose() {
    const result = await py().backup_dir();
    if (!result.cancelled && !result.error) applySettings({ ...app.settings!, ...result });
  }

  async function now() {
    busy = true;
    report(await py().backup_now());
    busy = false;
    applySettings(await py().settings());
  }
</script>

<Section title={t("settings_backups")} icon="archive" {index}>
  <div class="dir">
    <span class="path mono" class:dim={!s.backup_dir} title={s.backup_dir}>{s.backup_dir || t("backup_no_dir")}</span>
    <Button size="sm" icon="folder" onclick={choose}>{t("backup_choose")}</Button>
  </div>
  <div class="two">
    <Field label={t("backup_interval")}>
      <Select
        value={String(s.backup_hours)}
        options={(app.options?.backup_hours ?? [0, 6, 12, 24, 72, 168]).map((h) => ({
          value: String(h),
          label: h === 0 ? t("backup_off") : t("backup_every", { hours: h }),
        }))}
        onchange={(v) => saveSettings({ backup_hours: Number(v) })}
      />
    </Field>
    <Field label={t("backup_keep")}>
      <Select
        value={String(s.backup_keep)}
        options={(app.options?.backup_keep ?? [3, 7, 14, 30]).map((k) => ({ value: String(k), label: t("backup_keep_n", { n: k }) }))}
        onchange={(v) => saveSettings({ backup_keep: Number(v) })}
      />
    </Field>
  </div>
  <p class="hint">
    {t("backup_last", { at: s.last_backup.replace("T", " ") || "-" })} · {app.master ? t("backup_encrypted") : t("backup_plain")}
  </p>
  <p class="hint mono selectable">{t("backup_restore_hint")}</p>
  <div class="buttons">
    <Button variant="accent" size="sm" icon="archive" {busy} disabled={!s.backup_dir} onclick={now}>{t("backup_now")}</Button>
  </div>
</Section>

<style>
  .dir {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .path {
    flex: 1;
    min-width: 0;
    padding: 8px 10px;
    border: 2px solid var(--t-line);
    background: var(--t-bg);
    font-size: 12.5px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .two {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px;
  }
</style>
