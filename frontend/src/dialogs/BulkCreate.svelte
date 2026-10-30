<script lang="ts">
  import { slide } from "svelte/transition";
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import Input from "../components/Input.svelte";
  import Modal from "../components/Modal.svelte";
  import Segmented from "../components/Segmented.svelte";
  import Select from "../components/Select.svelte";
  import Textarea from "../components/Textarea.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { app } from "../lib/store.svelte";
  import { toast } from "../lib/toast.svelte";

  let { close }: { close: (v?: boolean) => void } = $props();

  let form = $state({
    mode: "pattern",
    pattern: "fb-{n}",
    count: "10",
    start: "1",
    proxies: "",
    proxy_mode: "order",
    tags: "",
    status: "",
    timezone: "",
    locale: "",
    text: "",
    os_type: "windows",
    engine: "camoufox",
  });
  let error = $state<string | null>(null);
  let busy = $state(false);

  // A preview of the names the pattern gives.
  const preview = $derived.by(() => {
    const n = Math.min(Number(form.count) || 0, 4);
    const first = Number(form.start) || 1;
    const width = String(first + (Number(form.count) || 0) - 1).length;
    if (!form.pattern.includes("{n}") || n < 1) return "";
    const names = Array.from({ length: n }, (_, i) =>
      form.pattern.replace("{n}", String(first + i).padStart(Math.max(2, width), "0")),
    );
    return names.join(", ") + ((Number(form.count) || 0) > n ? ", ..." : "");
  });

  async function create() {
    busy = true;
    error = null;
    const result = await py().bulk_create(form);
    busy = false;
    if (result.error) return (error = result.error);
    toast(result.message ?? "", "ok");
    close(true);
  }
</script>

<Modal title={t("bulk_create_title")} subtitle={t("bulk_create_subtitle")} width={600} onclose={() => close()}>
  <Segmented
    bind:value={form.mode}
    options={[
      { value: "pattern", label: t("bulk_mode_pattern") },
      { value: "list", label: t("bulk_mode_list") },
    ]}
  />
  {#if form.mode === "pattern"}
    <div class="grid" transition:slide={{ duration: 260 }}>
      <div class="three">
        <Field label={t("bulk_pattern")} hint={t("bulk_pattern_hint")}>
          <Input bind:value={form.pattern} mono />
        </Field>
        <Field label={t("bulk_count")}>
          <Input bind:value={form.count} mono type="number" />
        </Field>
        <Field label={t("bulk_start")}>
          <Input bind:value={form.start} mono type="number" />
        </Field>
      </div>
      {#if preview}<p class="preview mono">→ {preview}</p>{/if}
      <Field label={t("bulk_proxies")} hint={t("bulk_proxies_hint")}>
        <Textarea bind:value={form.proxies} rows={4} mono placeholder="socks5://user:pass@203.0.113.10:1080" />
      </Field>
      <div class="two">
        <Field label={t("proxy_mode")}>
          <Select
            bind:value={form.proxy_mode}
            options={[
              { value: "order", label: t("proxy_mode_order") },
              { value: "random", label: t("proxy_mode_random") },
            ]}
          />
        </Field>
        <Field label={t("status")}>
          <Select
            bind:value={form.status}
            options={(app.options?.statuses ?? [""]).map((s) => ({ value: s, label: s ? t(`status_${s}`) : t("status_none") }))}
          />
        </Field>
      </div>
      <div class="three">
        <Field label={t("tags")}><Input bind:value={form.tags} placeholder="fb, us" /></Field>
        <Field label={t("timezone_optional")}><Input bind:value={form.timezone} mono placeholder="Europe/Berlin" /></Field>
        <Field label={t("locale_optional")}><Input bind:value={form.locale} mono placeholder="de-DE" /></Field>
      </div>
    </div>
  {:else}
    <div transition:slide={{ duration: 260 }}>
      <Field label={t("bulk_list")} hint={t("bulk_list_hint")}>
        <Textarea bind:value={form.text} rows={8} mono placeholder="fb-01;socks5://user:pass@203.0.113.10:1080;fb,us;note" />
      </Field>
    </div>
  {/if}
  <div class="two">
    <Field label={t("browser_engine")}>
      <Segmented
        bind:value={form.engine}
        options={[
          { value: "camoufox", label: "Camoufox" },
          { value: "chrome", label: "Chrome" },
        ]}
      />
    </Field>
    <Field label={t("operating_system")}>
      <Segmented
        bind:value={form.os_type}
        options={[
          { value: "windows", label: "Win" },
          { value: "macos", label: "Mac" },
          { value: "linux", label: "Linux" },
        ]}
      />
    </Field>
  </div>
  {#if error}<p class="err">{error}</p>{/if}
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
    <Button variant="accent" icon="layers" {busy} onclick={create}>{t("bulk_create_btn")}</Button>
  {/snippet}
</Modal>

<style>
  .grid {
    display: grid;
    gap: 14px;
  }
  .two {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px;
  }
  .three {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px;
  }
  .preview {
    margin: -4px 0 0;
    padding: 6px 10px;
    background: var(--t-fg);
    color: var(--t-accent);
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .err {
    margin: 0;
    color: var(--error);
    font-weight: 600;
    animation: shake 0.4s;
  }
</style>
