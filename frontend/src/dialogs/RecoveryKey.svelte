<script lang="ts">
  import Button from "../components/Button.svelte";
  import Modal from "../components/Modal.svelte";
  import { t } from "../lib/i18n.svelte";
  import { copy } from "../lib/clipboard";

  let { key, close }: { key: string; close: () => void } = $props();
  let copied = $state(false);
</script>

<Modal title={t("recovery_title")} subtitle={t("recovery_body")} tone="alert" width={520}>
  <code class="key mono selectable">{key}</code>
  {#snippet actions()}
    <Button
      icon={copied ? "check" : "copy"}
      onclick={async () => {
        copied = await copy(key);
      }}>{copied ? t("mcp_copied") : t("copy")}</Button
    >
    <Button variant="accent" icon="check" onclick={() => close()}>{t("recovery_saved")}</Button>
  {/snippet}
</Modal>

<style>
  .key {
    display: block;
    padding: 18px;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-bg);
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.06em;
    word-break: break-all;
    text-align: center;
  }
</style>
