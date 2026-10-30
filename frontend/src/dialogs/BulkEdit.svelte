<script lang="ts">
  import Button from "../components/Button.svelte";
  import Checkbox from "../components/Checkbox.svelte";
  import Field from "../components/Field.svelte";
  import Input from "../components/Input.svelte";
  import Modal from "../components/Modal.svelte";
  import Select from "../components/Select.svelte";
  import Textarea from "../components/Textarea.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { app } from "../lib/store.svelte";
  import { toast } from "../lib/toast.svelte";

  let { names, close }: { names: string[]; close: (v?: boolean) => void } = $props();

  const KEEP = "__keep__";
  let form = $state({ proxies: "", direct: false, proxy_mode: "order", status: KEEP, add_tags: "", remove_tags: "" });
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function apply() {
    busy = true;
    error = null;
    const result = await py().bulk_edit(names, { ...form, status: form.status === KEEP ? null : form.status });
    busy = false;
    if (result.error) return (error = result.error);
    toast(result.message ?? "", "ok");
    close(true);
  }
</script>

<Modal title={t("bulk_edit_title")} subtitle={t("selected_count", { count: names.length })} width={560} onclose={() => close()}>
  <Field label={t("bulk_proxies")} hint={t("bulk_edit_proxies_hint")}>
    <Textarea bind:value={form.proxies} rows={4} mono placeholder="socks5://user:pass@203.0.113.10:1080" />
  </Field>
  <Checkbox bind:checked={form.direct} label={t("bulk_make_direct")} />
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
        options={[
          { value: KEEP, label: t("bulk_keep_status") },
          ...(app.options?.statuses ?? [""]).map((s) => ({ value: s, label: s ? t(`status_${s}`) : t("status_none") })),
        ]}
      />
    </Field>
  </div>
  <div class="two">
    <Field label={t("bulk_add_tags")}><Input bind:value={form.add_tags} placeholder="fb, us" /></Field>
    <Field label={t("bulk_remove_tags")}><Input bind:value={form.remove_tags} placeholder="old" /></Field>
  </div>
  {#if error}<p class="err">{error}</p>{/if}
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
    <Button variant="accent" icon="check" {busy} onclick={apply}>{t("apply")}</Button>
  {/snippet}
</Modal>

<style>
  .two {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px;
  }
  .err {
    margin: 0;
    color: var(--error);
    font-weight: 600;
  }
</style>
