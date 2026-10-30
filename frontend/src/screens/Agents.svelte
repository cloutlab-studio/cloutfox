<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../components/Button.svelte";
  import Checkbox from "../components/Checkbox.svelte";
  import Icon from "../components/Icon.svelte";
  import { py, type McpInfo } from "../lib/bridge";
  import { copy } from "../lib/clipboard";
  import { t } from "../lib/i18n.svelte";
  import { play } from "../lib/sound";
  import { toast } from "../lib/toast.svelte";

  let info = $state<McpInfo | null>(null);
  let health = $state<{ ok: boolean; error?: string } | null>(null);
  let client = $state("claude-code");
  let realToken = $state(false);

  const current = $derived(info?.configs.find((c) => c.id === client) ?? info?.configs[0]);

  async function load() {
    info = await py().mcp_info(realToken);
  }

  onMount(async () => {
    await load();
    health = await py().mcp_health();
  });

  async function copyText(text: string) {
    if (await copy(text)) toast(t("mcp_copied"), "ok");
  }
</script>

<section class="page">
  <header>
    <h1 class="display">{t("mcp_title")}</h1>
    <p class="intro">{t("mcp_intro")}</p>
    <div class="status mono">
      <span class="endpoint selectable">{t("mcp_endpoint", { url: info?.url ?? "" })}</span>
      {#if health}
        <span class="health" class:ok={health.ok}>
          {health.ok ? t("mcp_status_ok") : t("mcp_status_down", { error: health.error ?? "" })}
        </span>
      {/if}
    </div>
  </header>

  <div class="steps">
    <article class="step" style:animation-delay="60ms">
      <h2 class="label"><span class="n">1</span>{t("mcp_pick_client").replace(/^1\.\s*/, "")}</h2>
      <div class="clients">
        {#each info?.configs ?? [] as c (c.id)}
          <button
            type="button"
            class:on={c.id === client}
            data-press
            onclick={() => {
              client = c.id;
              play("toggle");
            }}>{c.name}</button
          >
        {/each}
      </div>
    </article>

    <article class="step" style:animation-delay="140ms">
      <h2 class="label"><span class="n">2</span>{t("mcp_paste_into", { where: current?.where ?? "" }).replace(/^2\.\s*/, "")}</h2>
      <div class="code">
        <pre class="mono selectable">{current?.code ?? ""}</pre>
        <Button variant="accent" size="sm" icon="copy" onclick={() => copyText(current?.code ?? "")}>{t("mcp_copy")}</Button>
      </div>
      {#if current?.id === "claude-desktop"}<p class="note">{t("mcp_desktop_note")}</p>{/if}
      {#if info?.has_token}
        <Checkbox bind:checked={realToken} label={t("mcp_show_token")} onchange={load} />
      {/if}
    </article>

    <article class="step" style:animation-delay="220ms">
      <h2 class="label"><span class="n">3</span>{t("mcp_restart").replace(/^3\.\s*/, "")}</h2>
      <button type="button" class="prompt" data-press onclick={() => copyText(t("mcp_example_prompt"))}>
        <span>“{t("mcp_example_prompt")}”</span>
        <Icon name="copy" size={16} />
      </button>
      <p class="note dim">{t("mcp_security_note")}</p>
    </article>
  </div>
</section>

<style>
  .page {
    height: 100%;
    overflow: auto;
    padding: 28px 32px 48px;
  }
  header {
    max-width: 900px;
  }
  h1 {
    margin: 0;
    font-size: 48px;
  }
  .intro {
    margin: 14px 0 0;
    font-size: 15px;
    line-height: 1.5;
    color: var(--t-muted);
  }
  .status {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-top: 14px;
    font-size: 12.5px;
  }
  .endpoint {
    padding: 4px 8px;
    background: var(--t-fg);
    color: var(--t-accent);
  }
  .health {
    padding: 4px 8px;
    border: 2px solid var(--error);
    color: var(--error);
    font-weight: 600;
  }
  .health.ok {
    border-color: var(--success);
    color: var(--success);
  }
  .steps {
    display: grid;
    gap: 22px;
    margin-top: 28px;
    max-width: 900px;
  }
  .step {
    display: grid;
    gap: 14px;
    padding: 20px 22px;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard);
    animation: rise 0.5s var(--t-ease) backwards;
  }
  h2 {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 0;
    font-size: 12px;
  }
  .n {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    background: var(--t-accent);
    border: 2px solid var(--t-line);
    font: 900 16px var(--font-display);
    transform: rotate(-6deg);
  }
  .clients {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
  .clients button {
    padding: 8px 14px;
    border: 2px solid var(--t-line);
    background: var(--t-surface);
    font: 600 12px var(--font-mono);
    box-shadow: 3px 3px 0 var(--t-line);
    transition:
      transform var(--t-dur) var(--t-ease),
      box-shadow var(--t-dur) var(--t-ease);
  }
  .clients button:hover {
    transform: translate(-2px, -2px);
    box-shadow: 5px 5px 0 var(--t-line);
  }
  .clients button.on {
    background: var(--t-accent);
    transform: translate(3px, 3px);
    box-shadow: none;
  }
  .code {
    position: relative;
  }
  pre {
    margin: 0;
    padding: 16px 18px;
    border: 2px solid var(--t-line);
    background: var(--rail);
    color: var(--rail-ink);
    font-size: 12.5px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .code :global(.btn) {
    position: absolute;
    top: 10px;
    right: 10px;
  }
  .note {
    margin: 0;
    font-size: 12.5px;
    color: var(--warning);
  }
  .note.dim {
    color: var(--dim);
  }
  .prompt {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 16px;
    border: 2px dashed var(--t-line);
    background: var(--t-bg);
    font-size: 15px;
    font-style: italic;
    text-align: left;
  }
  .prompt span {
    flex: 1;
  }
  .prompt:hover {
    border-style: solid;
    background: var(--t-accent);
  }
</style>
