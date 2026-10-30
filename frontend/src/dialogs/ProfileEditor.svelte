<script lang="ts">
  import { onMount } from "svelte";
  import { slide } from "svelte/transition";
  import Button from "../components/Button.svelte";
  import Checkbox from "../components/Checkbox.svelte";
  import Drawer from "../components/Drawer.svelte";
  import Field from "../components/Field.svelte";
  import GeoReport from "../components/GeoReport.svelte";
  import Icon from "../components/Icon.svelte";
  import Input from "../components/Input.svelte";
  import Segmented from "../components/Segmented.svelte";
  import Select from "../components/Select.svelte";
  import Textarea from "../components/Textarea.svelte";
  import Warning from "../components/Warning.svelte";
  import { py, type GeoReport as Geo, type ProfileDetail } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { play } from "../lib/sound";
  import { app, loadOptions } from "../lib/store.svelte";
  import { toast } from "../lib/toast.svelte";

  // Create (no name) or edit a profile. Identity on top, organisation under
  // "More": the same split as update_profile / set_meta.
  let { name = null, close }: { name?: string | null; close: (saved?: boolean) => void } = $props();

  const editing = $derived(name !== null);
  let form = $state({
    name: "",
    proxy: "",
    os_type: "windows",
    engine: "camoufox",
    timezone: "",
    locale: "",
    tags: "",
    notes: "",
    status: "",
    start_urls: "",
    proxy_rotate_url: "",
    extensions: [] as string[],
  });
  let detail = $state<ProfileDetail | null>(null);
  let extra = $state(false);
  let errors = $state<Record<string, string>>({});
  let busy = $state(false);
  let proxyCheck = $state<{ ok?: boolean; message?: string; error?: string } | null>(null);
  let proxyBusy = $state(false);
  let geo = $state<(Partial<Geo> & { error?: string }) | null>(null);
  let geoBusy = $state(false);

  const options = $derived(app.options);
  const extensions = $derived((options?.extensions ?? []).filter((e) => e.engine === form.engine));

  onMount(async () => {
    if (!app.options) await loadOptions();
    if (name === null) return;
    detail = await py().profile_detail(name);
    if (!detail) return close();
    form = {
      name: detail.name,
      proxy: detail.proxy,
      os_type: detail.os,
      engine: detail.engine,
      timezone: detail.timezone,
      locale: detail.locale,
      tags: detail.tags,
      notes: detail.notes,
      status: detail.status,
      start_urls: detail.start_urls,
      proxy_rotate_url: detail.proxy_rotate_url,
      extensions: [...detail.extensions],
    };
    extra = Boolean(
      detail.tags || detail.notes || detail.status || detail.start_urls || detail.proxy_rotate_url || detail.extensions.length,
    );
  });

  function toggleExtension(id: string, on: boolean) {
    form.extensions = on ? [...form.extensions, id] : form.extensions.filter((e) => e !== id);
  }

  async function save() {
    busy = true;
    errors = {};
    // Only the extensions made for this engine; the bridge keeps uninstalled ones.
    const ids = new Set(extensions.map((e) => e.id));
    const payload = { ...form, extensions: form.extensions.filter((e) => ids.has(e)) };
    const problem = await py().profile_save(editing ? name : null, payload);
    busy = false;
    if (problem) {
      errors = { [problem.field]: problem.error };
      if (problem.field === "extra") extra = true;
      play("error");
      return;
    }
    toast(editing ? t("updated_profile", { old: name, new: form.name }) : t("created_profile", { name: form.name }), "ok");
    close(true);
  }

  async function checkProxy() {
    proxyBusy = true;
    proxyCheck = await py().check_proxy(form.proxy);
    proxyBusy = false;
    play(proxyCheck.ok ? "done" : "error");
  }

  async function checkIp() {
    geoBusy = true;
    geo = null;
    geo = await py().check_geo(form.proxy, form.timezone, form.locale);
    geoBusy = false;
    play(geo.exit_ip && !geo.warnings?.length ? "done" : "error");
  }
</script>

<Drawer
  title={editing ? t("edit_profile") : t("create_new_profile")}
  subtitle={editing ? t("editing_profile", { name }) : t("configure_identity")}
  onclose={() => close()}
>
  <Field label={t("profile_name")} error={errors.name}>
    <Input
      bind:value={form.name}
      placeholder={t("enter_profile_name")}
      autofocus={!editing}
      invalid={Boolean(errors.name)}
      onenter={save}
    />
  </Field>

  <div class="two">
    <Field label={t("browser_engine")} hint={editing ? t("engine_locked") : null}>
      {#if editing}
        <Select
          value={form.engine}
          disabled
          options={[
            { value: "camoufox", label: t("engine_camoufox") },
            { value: "chrome", label: t("engine_chrome") },
          ]}
        />
      {:else}
        <Segmented
          bind:value={form.engine}
          options={[
            { value: "camoufox", label: "Camoufox" },
            { value: "chrome", label: "Chrome" },
          ]}
        />
      {/if}
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
  {#if form.engine === "chrome" && !editing}
    <div transition:slide={{ duration: 260 }}><Warning text={t("engine_chrome_note")} /></div>
  {/if}

  <Field
    label={t("proxy_optional")}
    hint={detail?.wireguard ? t("wireguard_proxy_note", { endpoint: detail.wireguard }) : t("proxy_format_hint")}
    error={errors.proxy}
  >
    <Input bind:value={form.proxy} mono placeholder="socks5://user:pass@host:port" invalid={Boolean(errors.proxy)} />
  </Field>
  <div class="row">
    <Button icon="wifi" size="sm" busy={proxyBusy} onclick={checkProxy}>{proxyBusy ? t("proxy_checking") : t("check_proxy")}</Button>
    <Button icon="globe" size="sm" busy={geoBusy} onclick={checkIp}>{geoBusy ? t("ip_checking") : t("check_ip")}</Button>
  </div>
  {#if proxyCheck}
    <p class="result" class:ok={proxyCheck.ok} transition:slide={{ duration: 200 }}>
      {proxyCheck.error ?? proxyCheck.message}
    </p>
  {/if}

  <div class="two">
    <Field label={t("timezone_optional")}>
      <Input bind:value={form.timezone} mono placeholder="Europe/Berlin" />
    </Field>
    <Field label={t("locale_optional")}>
      <Input bind:value={form.locale} mono placeholder="de-DE" />
    </Field>
  </div>
  <p class="hint">{t("geo_follow_hint")}</p>
  {#if errors.geo}<p class="err">{errors.geo}</p>{/if}
  {#if geo}
    <div transition:slide={{ duration: 260 }}>
      <GeoReport report={geo} onlocale={(v) => (form.locale = v)} />
    </div>
  {/if}

  <button
    type="button"
    class="more"
    class:open={extra}
    data-press
    onclick={() => {
      extra = !extra;
      play("toggle");
    }}
  >
    <Icon name="chevron" size={16} />
    <span class="label">{t("profile_extra")}</span>
  </button>

  {#if extra}
    <div class="extra" transition:slide={{ duration: 320 }}>
      <div class="two">
        <Field label={t("tags")} hint={t("tags_hint")}>
          <Input bind:value={form.tags} placeholder="fb, us, client-a" />
        </Field>
        <Field label={t("status")}>
          <Select
            bind:value={form.status}
            options={(options?.statuses ?? [""]).map((s) => ({ value: s, label: s ? t(`status_${s}`) : t("status_none") }))}
          />
        </Field>
      </div>
      <Field label={t("notes")}>
        <Textarea bind:value={form.notes} rows={3} maxlength={2000} />
      </Field>
      <Field label={t("start_urls")} hint={t("start_urls_hint")}>
        <Textarea bind:value={form.start_urls} rows={3} mono placeholder="https://www.facebook.com/" />
      </Field>
      <Field label={t("rotate_url")} hint={t("rotate_url_hint")}>
        <Input bind:value={form.proxy_rotate_url} type="password" reveal mono placeholder="https://provider.example/api/change-ip?key=..." />
      </Field>
      <Field label={t("extensions")}>
        <div class="exts">
          {#each extensions as e (e.id)}
            <Checkbox
              checked={form.extensions.includes(e.id)}
              label={`${e.name} ${e.version}`.trim()}
              onchange={(v) => toggleExtension(e.id, v)}
            />
          {:else}
            <span class="hint">{t("extensions_none")}</span>
          {/each}
        </div>
      </Field>
      {#if errors.extra}<p class="err">{errors.extra}</p>{/if}
    </div>
  {/if}

  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
    <Button variant="accent" size="lg" icon={editing ? "check" : "plus"} {busy} onclick={save}>
      {editing ? t("save_changes") : t("create_profile_btn")}
    </Button>
  {/snippet}
</Drawer>

<style>
  .two {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px;
  }
  .row {
    display: flex;
    gap: 12px;
    margin-top: -4px;
  }
  .result {
    margin: 0;
    padding: 8px 12px;
    border-left: 6px solid var(--error);
    background: var(--t-bg);
    color: var(--error);
    font: 600 12.5px var(--font-mono);
    overflow-wrap: anywhere;
  }
  .result.ok {
    border-color: var(--success);
    color: var(--success);
  }
  .hint {
    margin: -8px 0 0;
    font-size: 12px;
    color: var(--dim);
  }
  .err {
    margin: 0;
    color: var(--error);
    font-weight: 600;
    font-size: 12.5px;
  }
  .more {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 0;
    border: 0;
    border-top: var(--t-border-w) solid var(--t-line);
    background: none;
    text-align: left;
  }
  .more :global(svg) {
    transition: transform var(--t-dur) var(--t-ease);
  }
  .more.open :global(svg) {
    transform: rotate(90deg);
  }
  .more:hover .label {
    background: var(--t-accent);
  }
  .extra {
    display: grid;
    gap: 16px;
  }
  .exts {
    display: grid;
    gap: 8px;
  }
</style>
