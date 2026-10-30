<script lang="ts">
  import Button from "../components/Button.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { app, refresh } from "../lib/store.svelte";
  import { report } from "../lib/toast.svelte";

  // An agent asked for a human: a takeover card until someone answers.
  const request = $derived(app.help[0]);
  let busy = $state(false);

  async function answer(done: boolean) {
    if (!request) return;
    busy = true;
    report(await py().answer_help(request.id, done));
    busy = false;
    void refresh();
  }
</script>

{#if request}
  <div class="takeover" role="alertdialog" aria-label={t("help_title")}>
    <div class="stripes" aria-hidden="true"></div>
    {#key request.id}
      <div class="card">
        <span class="badge mono">{t("help_badge")}{app.help.length > 1 ? ` · ${app.help.length}` : ""}</span>
        <h2 class="display">{t("help_title")}</h2>
        <p class="who mono">{t("help_profile", { name: request.profile })}</p>
        <blockquote class="reason selectable">{request.reason}</blockquote>
        <p class="hint">{t("help_hint")}</p>
        <div class="actions">
          <Button size="lg" icon="eye" onclick={async () => report(await py().show_browser(request.profile))}>
            {t("help_show")}
          </Button>
          <span class="grow"></span>
          <Button size="lg" variant="ghost" disabled={busy} onclick={() => answer(false)}>{t("help_decline")}</Button>
          <Button size="lg" variant="accent" icon="check" {busy} onclick={() => answer(true)}>{t("help_done")}</Button>
        </div>
      </div>
    {/key}
  </div>
{/if}

<style>
  .takeover {
    position: fixed;
    inset: 0;
    z-index: 300;
    display: grid;
    place-items: center;
    background: rgb(10 10 10 / 0.62);
    animation: fade 0.3s linear;
  }
  .stripes {
    position: absolute;
    inset: 0;
    overflow: hidden;
  }
  /* One stripe period wider than the screen and moved by a period, so the
     compositor runs it without redrawing the page. */
  .stripes::before {
    content: "";
    position: absolute;
    inset: 0 0 0 -79.2px;
    background: repeating-linear-gradient(-45deg, rgb(255 92 138 / 0.22) 0 14px, transparent 14px 56px);
    background-size: 79.2px 79.2px;
    animation: slide 1.4s linear infinite;
  }
  .card {
    position: relative;
    width: min(640px, calc(100vw - 64px));
    display: grid;
    gap: 14px;
    padding: 30px 32px 28px;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: 14px 14px 0 var(--t-accent-2);
    animation: slam 0.6s var(--t-ease);
  }
  .badge {
    justify-self: start;
    padding: 4px 8px;
    background: var(--t-accent-2);
    border: 2px solid var(--t-line);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    animation: blink 1s steps(1) 3;
  }
  h2 {
    margin: 0;
    font-size: 48px;
  }
  .who {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }
  .reason {
    margin: 0;
    padding: 16px 18px;
    border-left: 8px solid var(--t-fg);
    background: var(--t-bg);
    font-size: 17px;
    line-height: 1.45;
    overflow-wrap: anywhere;
    max-height: 220px;
    overflow: auto;
  }
  .hint {
    margin: 0;
    color: var(--t-muted);
    font-size: 13.5px;
  }
  .actions {
    display: flex;
    gap: 14px;
    margin-top: 8px;
  }
  .grow {
    flex: 1;
  }
  @keyframes fade {
    from {
      opacity: 0;
    }
  }
  @keyframes slide {
    to {
      transform: translateX(79.2px);
    }
  }
  @keyframes slam {
    from {
      opacity: 0;
      transform: scale(1.4) rotate(4deg);
    }
    55% {
      opacity: 1;
    }
  }
</style>
