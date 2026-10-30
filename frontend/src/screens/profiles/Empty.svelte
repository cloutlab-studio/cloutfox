<script lang="ts">
  import Button from "../../components/Button.svelte";
  import { fox } from "../../lib/assets";
  import { t } from "../../lib/i18n.svelte";
  import * as act from "../../lib/actions";

  let { onclick }: { onclick: () => void } = $props();
</script>

<div class="empty">
  <img src={fox} alt="" />
  <h2 class="display">{t("no_profiles_yet")}</h2>
  <p>{t("create_profile_hint")}</p>
  <div class="row">
    <Button variant="accent" size="lg" icon="plus" {onclick}>{t("create_profile_btn")}</Button>
    <Button size="lg" icon="layers" onclick={act.bulkCreate}>{t("bulk_create_btn")}</Button>
    <Button size="lg" icon="import" onclick={act.importProfiles}>{t("import")}</Button>
  </div>
</div>

<style>
  .empty {
    flex: 1;
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 14px;
    padding: 48px;
    text-align: center;
  }
  img {
    width: 120px;
    animation: bob 3s ease-in-out infinite;
    animation-play-state: var(--loops);
  }
  h2 {
    margin: 8px 0 0;
    font-size: 48px;
  }
  p {
    margin: 0;
    color: var(--t-muted);
  }
  .row {
    display: flex;
    gap: 16px;
    margin-top: 12px;
  }
  @keyframes bob {
    50% {
      transform: translateY(-8px) rotate(-3deg);
    }
  }
</style>
