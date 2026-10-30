<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../components/Button.svelte";
  import Icon, { type IconName } from "../components/Icon.svelte";
  import Modal from "../components/Modal.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { open } from "../lib/overlay.svelte";
  import { play } from "../lib/sound";
  import { report } from "../lib/toast.svelte";
  import Confirm from "./Confirm.svelte";

  let { name, close }: { name: string; close: () => void } = $props();
  let fingerprint = $state("");
  let busy = $state<string | null>(null);

  onMount(async () => {
    fingerprint = (await py().cookies_info(name)).fingerprint;
  });

  async function run(id: string, work: () => Promise<{ error?: string; message?: string; cancelled?: boolean }>) {
    busy = id;
    const result = await work();
    busy = null;
    if (!result.cancelled) report(result);
  }

  async function reset() {
    const ok = await open<boolean>(Confirm, {
      title: t("confirm_reset_fingerprint", { name }),
      body: t("fingerprint_reset_hint"),
      action: t("fingerprint_reset"),
    });
    if (!ok) return;
    await run("reset", () => py().fingerprint_reset(name));
    fingerprint = (await py().cookies_info(name)).fingerprint;
  }

  const tiles: { id: string; icon: IconName; title: string; hint: string; go: () => void }[] = [
    {
      id: "json",
      icon: "export",
      title: t("cookie_export_json"),
      hint: t("cookie_export_json_hint"),
      go: () => run("json", () => py().cookies_export(name, "json")),
    },
    {
      id: "netscape",
      icon: "file",
      title: t("cookie_export_netscape"),
      hint: t("cookie_export_netscape_hint"),
      go: () => run("netscape", () => py().cookies_export(name, "netscape")),
    },
    {
      id: "import",
      icon: "import",
      title: t("cookie_import"),
      hint: t("cookie_import_hint"),
      go: () => run("import", () => py().cookies_import(name)),
    },
    { id: "reset", icon: "fingerprint", title: t("fingerprint_reset"), hint: t("fingerprint_reset_hint"), go: reset },
  ];
</script>

<Modal title={t("cookie_dialog_title")} subtitle={t("cookie_dialog_hint", { name })} width={620} onclose={close}>
  <div class="tiles">
    {#each tiles as tile, i (tile.id)}
      <button
        type="button"
        class="tile"
        class:busy={busy === tile.id}
        disabled={busy !== null}
        data-press
        style:animation-delay="{60 + i * 50}ms"
        onclick={() => {
          play("tap");
          tile.go();
        }}
      >
        <span class="ico"><Icon name={tile.icon} size={22} /></span>
        <span class="title">{tile.title}</span>
        <span class="hint">{tile.hint}</span>
      </button>
    {/each}
  </div>
  <p class="fp mono selectable"><Icon name="fingerprint" size={16} /> {fingerprint || "..."}</p>
  {#snippet actions()}
    <Button onclick={close}>{t("close_btn")}</Button>
  {/snippet}
</Modal>

<style>
  .tiles {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px;
  }
  .tile {
    display: grid;
    grid-template-columns: auto 1fr;
    grid-template-rows: auto auto;
    column-gap: 12px;
    row-gap: 4px;
    padding: 14px;
    border: 2px solid var(--t-line);
    background: var(--t-surface);
    text-align: left;
    box-shadow: 4px 4px 0 var(--t-line);
    animation: rise 0.4s var(--t-ease) backwards;
    transition:
      transform var(--t-dur) var(--t-ease),
      box-shadow var(--t-dur) var(--t-ease),
      background-color 0.12s linear;
  }
  .tile:hover:not(:disabled) {
    background: var(--t-accent);
    transform: translate(-2px, -2px) rotate(-0.6deg);
    box-shadow: 6px 6px 0 var(--t-line);
  }
  .tile:active:not(:disabled) {
    transform: translate(4px, 4px);
    box-shadow: none;
  }
  .tile:disabled {
    opacity: 0.55;
    cursor: default;
  }
  .tile.busy {
    position: relative;
    isolation: isolate;
    overflow: hidden;
    opacity: 1;
  }
  /* The stripes run on a layer one tile wider, moved by transform: a looping
     background-position would redraw the page on every frame. */
  .tile.busy::before {
    content: "";
    position: absolute;
    inset: 0 0 0 -28px;
    z-index: -1;
    background: repeating-linear-gradient(-45deg, var(--t-accent) 0 10px, var(--t-surface) 10px 20px);
    background-size: 28px 28px;
    animation: stripes 0.6s linear infinite;
    animation-play-state: var(--loops);
  }
  .ico {
    grid-row: span 2;
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border: 2px solid var(--t-line);
    background: var(--t-bg);
  }
  .title {
    font: 600 12.5px var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .hint {
    font-size: 12px;
    color: var(--t-muted);
  }
  .fp {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0;
    padding: 10px 12px;
    background: var(--t-fg);
    color: var(--t-bg);
    font-size: 12.5px;
  }
  @keyframes stripes {
    to {
      transform: translateX(28px);
    }
  }
</style>
