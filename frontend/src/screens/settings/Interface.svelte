<script lang="ts">
  import Button from "../../components/Button.svelte";
  import Field from "../../components/Field.svelte";
  import Segmented from "../../components/Segmented.svelte";
  import Switch from "../../components/Switch.svelte";
  import { language, t } from "../../lib/i18n.svelte";
  import { play, type Voice } from "../../lib/sound";
  import { app, saveSettings, setLanguage } from "../../lib/store.svelte";
  import Section from "./Section.svelte";

  let { index }: { index: number } = $props();
  const s = $derived(app.settings!);
  let volume = $state(app.settings?.sound_volume ?? 60);
  const voices: Voice[] = ["launch", "live", "stop", "done", "error", "help"];
  let demo = 0;
</script>

<Section title={t("settings_interface")} icon="sparkle" {index}>
  <Field label={t("ui_language")}>
    <Segmented
      value={language()}
      options={[
        { value: "ru", label: "Русский" },
        { value: "en", label: "English" },
      ]}
      onchange={(v) => setLanguage(v)}
    />
  </Field>
  <Switch checked={s.sound} label={t("ui_sound")} onchange={(v) => saveSettings({ sound: v })} />
  <p class="hint">{t("ui_sound_hint")}</p>
  <Field label={t("ui_volume", { n: volume })}>
    <div class="vol">
      <input
        type="range"
        min="0"
        max="100"
        step="5"
        bind:value={volume}
        disabled={!s.sound}
        style:--v="{volume}%"
        onchange={async () => {
          await saveSettings({ sound_volume: Number(volume) });
          play("live");
        }}
      />
      <Button
        size="sm"
        icon="volume"
        disabled={!s.sound}
        onclick={() => {
          play(voices[demo++ % voices.length], true);
        }}>{t("ui_sound_test")}</Button
      >
    </div>
  </Field>
  <Field label={t("ui_motion")}>
    <Segmented
      value={s.motion}
      options={[
        { value: "system", label: t("motion_system") },
        { value: "full", label: t("motion_full") },
        { value: "reduced", label: t("motion_reduced") },
      ]}
      onchange={(v) => saveSettings({ motion: v as "system" | "full" | "reduced" })}
    />
  </Field>
  <Switch checked={s.cursor} label={t("ui_cursor")} onchange={(v) => saveSettings({ cursor: v })} />
</Section>

<style>
  .vol {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  input[type="range"] {
    flex: 1;
    height: 18px;
    appearance: none;
    background: linear-gradient(90deg, var(--t-accent) var(--v), var(--t-bg-2) 0);
    border: 2px solid var(--t-line);
  }
  input[type="range"]::-webkit-slider-thumb {
    appearance: none;
    width: 18px;
    height: 26px;
    background: var(--t-fg);
    border: 2px solid var(--t-bg);
    box-shadow: 2px 2px 0 var(--t-fg);
  }
  input[type="range"]:disabled {
    opacity: 0.5;
  }
</style>
