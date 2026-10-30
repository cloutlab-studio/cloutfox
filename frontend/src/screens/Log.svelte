<script lang="ts">
  import { tick } from "svelte";
  import Button from "../components/Button.svelte";
  import Segmented from "../components/Segmented.svelte";
  import { copy } from "../lib/clipboard";
  import { t } from "../lib/i18n.svelte";
  import { app } from "../lib/store.svelte";

  let box: HTMLDivElement;
  let kind = $state("all");
  let follow = $state(true);

  const bad = (text: string) => /error|ошибк|fail|не удалось|LAUNCH_FAILED/i.test(text);
  const lines = $derived(kind === "errors" ? app.log.filter((l) => bad(l.text)) : app.log);

  $effect(() => {
    void lines.length;
    if (follow) void tick().then(() => box && (box.scrollTop = box.scrollHeight));
  });
</script>

<section class="page">
  <header>
    <h1 class="display">{t("activity_log")}</h1>
    <div class="tools">
      <span class="label dim">{t("log_entries", { count: lines.length })}</span>
      <Segmented
        bind:value={kind}
        options={[
          { value: "all", label: t("log_all") },
          { value: "errors", label: t("log_errors") },
        ]}
      />
      <Button size="sm" icon="copy" onclick={() => copy(lines.map((l) => `${l.at} ${l.text}`).join("\n"))}>{t("copy")}</Button>
    </div>
  </header>
  <div
    class="term mono selectable"
    bind:this={box}
    onscroll={() => (follow = box.scrollTop + box.clientHeight >= box.scrollHeight - 24)}
  >
    {#each lines as line (line.id)}
      <div class="line" class:bad={bad(line.text)}>
        <span class="at">{line.at}</span>
        <span class="text">{line.text}</span>
      </div>
    {:else}
      <p class="none">{t("log_no_activity")}</p>
    {/each}
    <div class="caret" aria-hidden="true">▌</div>
  </div>
</section>

<style>
  .page {
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 28px 32px;
  }
  header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
  }
  h1 {
    margin: 0;
    font-size: 64px;
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .term {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 16px 0;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--rail);
    color: var(--rail-ink);
    box-shadow: var(--t-hard);
    font-size: 12.5px;
    line-height: 1.6;
  }
  .line {
    display: grid;
    grid-template-columns: 84px 1fr;
    gap: 12px;
    padding: 1px 18px;
    animation: type-in 0.25s steps(6);
  }
  .line:hover {
    background: var(--rail-deep);
  }
  .at {
    color: var(--rail-muted);
  }
  .text {
    overflow-wrap: anywhere;
  }
  .bad .text {
    color: #ff7a8c;
  }
  .none {
    margin: 0;
    padding: 0 18px;
    color: var(--rail-muted);
  }
  .caret {
    padding: 0 18px;
    color: var(--t-accent);
    animation: blink 1s steps(1) infinite;
    animation-play-state: var(--loops);
  }
  @keyframes type-in {
    from {
      clip-path: inset(0 100% 0 0);
    }
  }
</style>
