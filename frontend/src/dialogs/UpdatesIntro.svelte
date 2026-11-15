<script lang="ts">
  import Button from "../components/Button.svelte";
  import Modal from "../components/Modal.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";

  // Asked once, on the first start: an update check is the only thing CloutFox
  // ever sends to the internet on its own, so the person says yes first.
  let { close }: { close: (v?: boolean) => void } = $props();

  async function answer(on: boolean) {
    await py().settings_update({ update_asked: true, auto_update_check: on });
    close(on);
  }
</script>

<Modal title={t("update_auto_title")} width={480} onclose={() => answer(false)}>
  <p class="hint">{t("update_auto_body")}</p>
  {#snippet actions()}
    <Button variant="ghost" onclick={() => answer(false)}>{t("update_auto_off")}</Button>
    <Button variant="accent" icon="refresh" onclick={() => answer(true)}>{t("update_auto_on")}</Button>
  {/snippet}
</Modal>
