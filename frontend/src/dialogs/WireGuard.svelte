<script lang="ts">
  import { slide } from "svelte/transition";
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import GeoReport from "../components/GeoReport.svelte";
  import Modal from "../components/Modal.svelte";
  import Textarea from "../components/Textarea.svelte";
  import { py, type GeoReport as Geo } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { open } from "../lib/overlay.svelte";
  import { play } from "../lib/sound";
  import { report } from "../lib/toast.svelte";
  import Confirm from "./Confirm.svelte";

  // The saved config is never shown: the field only takes a new one.
  let { name, endpoint, close }: { name: string; endpoint: string | null; close: (v?: boolean) => void } = $props();

  let text = $state("");
  let error = $state<string | null>(null);
  let geo = $state<(Partial<Geo> & { error?: string }) | null>(null);
  let checking = $state(false);
  let saving = $state(false);

  async function load() {
    const result = await py().wireguard_load();
    if (result.error) error = result.error;
    else if (result.text) {
      text = result.text;
      error = null;
    }
  }

  async function check() {
    error = null;
    checking = true;
    geo = null;
    const result = await py().wireguard_check(name, text);
    checking = false;
    if (result.error && !result.exit_ip && result.sources === undefined) {
      error = result.error;
      play("error");
    } else {
      geo = result;
      play(result.exit_ip ? "done" : "error");
    }
  }

  async function save(value: string | null) {
    saving = true;
    const result = await py().wireguard_save(name, value);
    saving = false;
    if (result.error) return (error = result.error);
    report(result);
    close(true);
  }

  async function remove() {
    const ok = await open<boolean>(Confirm, {
      title: t("wireguard_remove") + "?",
      body: t("wireguard_current", { endpoint }),
      action: t("wireguard_remove"),
    });
    if (ok) await save(null);
  }
</script>

<Modal title={t("wireguard_title")} subtitle={name} width={600} onclose={() => close()}>
  <p class="status" class:on={endpoint}>
    {endpoint ? t("wireguard_current", { endpoint }) : t("wireguard_none")}
  </p>
  <p class="hint">{t("wireguard_hint")}</p>
  <Field label={t("wireguard_config")} {error}>
    <Textarea
      bind:value={text}
      rows={8}
      mono
      invalid={Boolean(error)}
      placeholder={"[Interface]\nPrivateKey = ...\nAddress = ...\n\n[Peer]\nPublicKey = ...\nEndpoint = ..."}
    />
  </Field>
  <div class="row">
    <Button icon="file" size="sm" onclick={load}>{t("wireguard_load")}</Button>
    <Button icon="globe" size="sm" busy={checking} onclick={check}>{checking ? t("ip_checking") : t("check_ip")}</Button>
    {#if endpoint}<Button icon="close" size="sm" variant="danger" onclick={remove}>{t("wireguard_remove")}</Button>{/if}
  </div>
  {#if geo}<div transition:slide={{ duration: 260 }}><GeoReport report={geo} /></div>{/if}
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
    <Button variant="accent" icon="tunnel" busy={saving} disabled={!text.trim()} onclick={() => save(text)}>
      {t("save_changes")}
    </Button>
  {/snippet}
</Modal>

<style>
  .status {
    margin: 0;
    padding: 10px 12px;
    border: 2px solid var(--t-line);
    font: 600 13px var(--font-mono);
    color: var(--dim);
  }
  .status.on {
    background: var(--live-tint);
    color: var(--live);
    border-color: var(--live);
  }
  .hint {
    margin: 0;
    font-size: 12.5px;
    color: var(--t-muted);
    line-height: 1.5;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
  }
</style>
