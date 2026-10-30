<script lang="ts">
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import Input from "../components/Input.svelte";
  import NewPassword from "../dialogs/NewPassword.svelte";
  import { fox } from "../lib/assets";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { open } from "../lib/overlay.svelte";
  import { play } from "../lib/sound";
  import { app, opened } from "../lib/store.svelte";

  let recovery = $state(false);
  let secret = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);
  let shake = $state(0);

  const word = "CLOUTFOX";

  async function submit() {
    if (!secret.trim() || busy) return;
    busy = true;
    error = null;
    const api = py();
    const result = recovery ? await api.unlock_recovery(secret) : await api.unlock(secret);
    busy = false;
    if (result.error) {
      error = result.error;
      shake++;
      play("error");
      return;
    }
    play("live");
    secret = "";
    await opened();
    if (recovery) {
      // Opened with the recovery key: the forgotten password is replaced now.
      await open(NewPassword, {
        title: t("master_change"),
        hint: t("recovery_used"),
        submit: (pw: string) => py().change_master(pw),
        forced: true,
      });
    }
  }
</script>

<main class="lock">
  <section class="poster" aria-hidden="true">
    <img src={fox} alt="" class="fox" />
    <h1 class="display word">
      {#each word.split("") as ch, i (i)}<span style:animation-delay="{120 + i * 70}ms">{ch}</span>{/each}
    </h1>
    <p class="tag mono">{t("app_subtitle")} · v{app.version}</p>
    <div class="ticker mono"><span>{t("lock_title")} ✦ {t("lock_title")} ✦ {t("lock_title")} ✦ {t("lock_title")} ✦ </span><span>{t("lock_title")} ✦ {t("lock_title")} ✦ {t("lock_title")} ✦ {t("lock_title")} ✦ </span></div>
  </section>

  {#key shake}
    <form
      class="card"
      class:shake={shake > 0}
      onsubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h2 class="display">{t("lock_title")}</h2>
      <Field
        label={recovery ? t("recovery_title") : t("password")}
        hint={recovery ? t("lock_recovery_hint") : t("lock_hint")}
        {error}
      >
        <Input
          bind:value={secret}
          type={recovery ? "text" : "password"}
          mono={recovery}
          invalid={Boolean(error)}
          autofocus
          reveal
          onenter={submit}
        />
      </Field>
      <Button variant="accent" size="lg" icon="unlock" type="submit" {busy} wide>{t("lock_open")}</Button>
      <button
        type="button"
        class="switch"
        data-press
        onclick={() => {
          recovery = !recovery;
          secret = "";
          error = null;
          play("toggle");
        }}>{recovery ? t("lock_use_password") : t("lock_use_recovery")}</button
      >
    </form>
  {/key}
</main>

<style>
  .lock {
    height: 100%;
    display: grid;
    grid-template-columns: 1.3fr 1fr;
    background: var(--rail);
    color: var(--rail-ink);
    overflow: hidden;
  }
  .poster {
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0 56px;
    border-right: var(--t-border-w) solid var(--rail-line);
    overflow: hidden;
  }
  .fox {
    width: 120px;
    height: 120px;
    animation: drop-in 0.8s var(--t-ease) both;
  }
  .word {
    margin: 28px 0 14px;
    font-size: clamp(56px, 7.4vw, 140px);
    line-height: 0.86;
    display: flex;
    white-space: nowrap;
  }
  .word span {
    display: inline-block;
    animation: letter 0.6s var(--t-ease) both;
  }
  .word span:nth-child(n + 6) {
    color: var(--t-accent);
  }
  .tag {
    margin: 0;
    color: var(--rail-muted);
    font-size: 13px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .ticker {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    width: max-content;
    padding: 10px 0;
    border-top: var(--t-border-w) solid var(--rail-line);
    background: var(--t-accent);
    color: var(--t-fg);
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    white-space: nowrap;
    animation: marquee 22s linear infinite;
    animation-play-state: var(--loops);
  }
  .ticker span {
    padding-right: 12px;
  }
  .card {
    align-self: center;
    justify-self: center;
    width: min(420px, calc(100% - 64px));
    display: grid;
    gap: 18px;
    padding: 30px;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    color: var(--t-fg);
    box-shadow: 10px 10px 0 var(--t-accent);
    animation: rise 0.6s 0.3s var(--t-ease) both;
  }
  .card.shake {
    animation: shake 0.45s;
  }
  h2 {
    margin: 0;
    font-size: 30px;
  }
  .switch {
    justify-self: start;
    padding: 0;
    border: 0;
    background: none;
    font-size: 13px;
    text-decoration: underline;
    text-decoration-thickness: 2px;
    text-underline-offset: 4px;
  }
  .switch:hover {
    color: var(--live);
  }
  @keyframes letter {
    from {
      opacity: 0;
      transform: translateY(60%) rotate(8deg);
    }
  }
  @keyframes drop-in {
    from {
      opacity: 0;
      transform: translateY(-40px) rotate(-12deg);
    }
  }
</style>
