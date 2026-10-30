<script lang="ts">
  let { text }: { text: string } = $props();
</script>

<p class="warning">
  <span class="mark" aria-hidden="true">!</span>
  <span>{text}</span>
</p>

<style>
  .warning {
    display: flex;
    gap: 12px;
    margin: 0;
    padding: 12px 14px;
    border: 2px solid var(--t-line);
    background: var(--warn-tint);
    color: var(--warn-text);
    font-size: 13px;
    line-height: 1.45;
  }
  .mark {
    flex: none;
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    background: var(--t-fg);
    color: var(--t-accent);
    font: 900 14px var(--font-display);
    transform: rotate(-6deg);
  }
</style>
